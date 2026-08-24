"""
Document ingestion: validate -> store -> chunk -> index.

JAVA: a @Service handling MultipartFile, plus the validation you would
normally scatter across a controller.

Everything hostile about file upload is handled here, in one place:
filenames, size, encoding, and per-user quota.
"""

import hashlib
import re
import unicodedata
import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, DocumentChunk


class IngestionError(Exception):
    """Anything the user did wrong. The route turns this into a 400/413/422."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def safe_display_name(filename: str) -> str:
    """
    Make a client-supplied filename safe to STORE AS TEXT and show back.

    It is never used to build a path - see storage_path() - but it still gets
    sanitised, because it will be rendered in a UI someday and
    "<script>alert(1)</script>.txt" is a perfectly legal filename.

    Path traversal is defeated by Path(...).name, which turns
    "../../../../etc/passwd" into "passwd".
    """
    name = Path(filename.replace("\\", "/")).name          # strip any directory
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name)          # keep it boring
    name = name.strip(". ") or "untitled"                  # no ".." , no ""
    return name[:255]


def check_extension(display_name: str) -> None:
    allowed = get_settings().allowed_extensions
    if Path(display_name).suffix.lower() not in allowed:
        raise IngestionError(
            f"Unsupported file type. Allowed: {', '.join(allowed)}",
            status_code=415,
        )


def decode_text(raw: bytes) -> str:
    """
    Bytes to str, defensively.

    Never trust the client's charset. Try UTF-8, fall back to latin-1 (which
    cannot fail), and reject anything that looks binary - a PNG renamed to
    .txt would otherwise be "ingested" as garbage chunks.
    """
    if b"\x00" in raw[:8192]:
        raise IngestionError("File looks binary, not text.", status_code=415)

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    if not text.strip():
        raise IngestionError("File is empty.", status_code=422)

    return text


def check_quota(db: Session, user_id: int) -> None:
    limit = get_settings().max_documents_per_user
    current = db.execute(
        select(func.count()).select_from(Document).where(Document.user_id == user_id)
    ).scalar_one()

    if current >= limit:
        raise IngestionError(
            f"Document limit reached ({limit}). Delete one first.",
            status_code=409,
        )


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", flags=re.MULTILINE)


def _word_safe_tail(text: str, overlap: int) -> str:
    """
    Last `overlap` characters, trimmed forward to a word boundary.

    A raw slice produces chunks starting mid-word ("terprise customers..."),
    which tokenises into garbage and never matches anything.
    """
    if overlap <= 0 or len(text) <= overlap:
        return text if overlap > 0 else ""

    tail = text[-overlap:]
    space = tail.find(" ")
    return tail[space + 1:] if space != -1 else ""


def _split_sections(text: str) -> list[tuple[str, str]]:
    """
    Split a markdown document into (heading, body) pairs.

    Text before the first heading is returned with an empty heading.
    """
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [("", text)]

    sections: list[tuple[str, str]] = []

    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.append(("", preamble))

    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((heading, body))

    return sections


def _pack(paragraphs: list[str], size: int, overlap: int) -> list[str]:
    """Greedily fill chunks up to `size`, carrying a word-safe overlap."""
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # a paragraph larger than the budget is cut on word boundaries
        while len(para) > size:
            cut = para.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            head, para = para[:cut].strip(), para[cut:].strip()
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)

        if not para:
            continue

        if not current:
            current = para
        elif len(current) + len(para) + 2 <= size:
            current = f"{current}\n\n{para}"
        else:
            chunks.append(current)
            tail = _word_safe_tail(current, overlap)
            current = f"{tail}\n\n{para}" if tail else para

    if current.strip():
        chunks.append(current.strip())

    return chunks


def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    """
    Split text into retrievable chunks.

    Three strategies, in order of preference:

    1. Q:/A: pairs become one chunk each - splitting a question from its
       answer would make both useless.
    2. Markdown headings become section boundaries, and the heading is
       PREPENDED to every chunk of its section. That repetition is deliberate:
       the body of "Support hours" rarely repeats the word "support", so
       without the heading a question about support hours cannot match it.
    3. Plain prose is packed paragraph by paragraph with a word-safe overlap,
       so a sentence spanning a boundary stays findable.
    """
    settings = get_settings()
    size = size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap

    text = text.strip()

    # 1. FAQ format
    if re.search(r"^\s*Q:", text, flags=re.MULTILINE):
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        if blocks:
            return blocks

    # 2 + 3. Section-aware packing
    chunks: list[str] = []

    for heading, body in _split_sections(text):
        prefix = f"{heading}\n\n" if heading else ""
        # reserve room for the heading so chunks stay within `size`
        budget = max(size - len(prefix), size // 2)

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        for piece in _pack(paragraphs, budget, overlap):
            chunks.append(f"{prefix}{piece}")

    return chunks or [text[:size]]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def storage_path(user_id: int) -> Path:
    """
    Build the on-disk path OURSELVES from a UUID.

    The client's filename never touches this. That is the whole defence
    against path traversal: there is no user input in the path to escape with.
    """
    base = Path(get_settings().storage_dir) / str(user_id)
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{uuid.uuid4().hex}.txt"


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------

def ingest(db: Session, user_id: int, filename: str, raw: bytes) -> Document:
    """
    Validate, store, chunk, and index one uploaded file.

    Returns the persisted Document. Raises IngestionError for anything the
    user can fix.
    """
    display_name = safe_display_name(filename)
    check_extension(display_name)
    check_quota(db, user_id)

    text = decode_text(raw)
    content_hash = hashlib.sha256(raw).hexdigest()

    # Same bytes uploaded twice? Return the existing document instead of
    # indexing a duplicate that would compete with itself in the ranking.
    existing = db.execute(
        select(Document).where(
            Document.user_id == user_id, Document.content_hash == content_hash
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    chunks = chunk_text(text)

    path = storage_path(user_id)
    path.write_text(text, encoding="utf-8")

    document = Document(
        user_id=user_id,
        filename=display_name,
        stored_path=str(path),
        size_bytes=len(raw),
        chunk_count=len(chunks),
        content_hash=content_hash,
    )
    db.add(document)
    db.flush()          # assigns document.id without committing yet

    db.add_all(
        DocumentChunk(
            document_id=document.id,
            user_id=user_id,
            position=i,
            content=chunk,
        )
        for i, chunk in enumerate(chunks)
    )

    db.commit()
    db.refresh(document)
    return document


def delete_document(db: Session, user_id: int, document_id: int) -> bool:
    """
    Delete a document, its chunks, and its file.

    The user_id filter is the authorization check - without it, any user could
    delete any document by guessing an id (IDOR).
    """
    document = db.execute(
        select(Document).where(
            Document.id == document_id, Document.user_id == user_id
        )
    ).scalar_one_or_none()

    if document is None:
        return False

    # Remove the file first; a leftover row is easier to notice than a
    # leftover file, and missing_ok means a half-deleted state still cleans up.
    Path(document.stored_path).unlink(missing_ok=True)

    db.delete(document)          # cascade removes the chunks
    db.commit()
    return True
