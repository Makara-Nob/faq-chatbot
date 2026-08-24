"""
Document upload and management.

JAVA: @PostMapping(consumes = MULTIPART_FORM_DATA_VALUE)
      public ApiResponse<DocumentOut> upload(@RequestParam MultipartFile file)
"""

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.ratelimit import api_limiter
from app.db.models import Document, DocumentChunk
from app.schemas.document import DocumentList, DocumentOut
from app.schemas.envelope import ApiResponse, ok
from app.services.ingestion import IngestionError, delete_document, ingest

router = APIRouter(prefix="/documents", tags=["documents"])

READ_CHUNK = 64 * 1024      # 64 KB at a time


async def read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    """
    Read an upload without trusting its declared size.

    `await upload.read()` with no argument would pull the WHOLE file into
    memory - so a 4 GB upload becomes a 4 GB allocation and the process dies.
    That is a one-line denial of service, and it is the single most common
    mistake in file-upload code.

    The Content-Length header is not a defence either: it is client-supplied.
    The only real limit is counting the bytes you actually read.
    """
    buffer = bytearray()

    while True:
        piece = await upload.read(READ_CHUNK)
        if not piece:
            break

        buffer.extend(piece)
        if len(buffer) > max_bytes:
            raise IngestionError(
                f"File too large. Limit is {max_bytes // 1024} KB.",
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )

    return bytes(buffer)


@router.post(
    "",
    response_model=ApiResponse[DocumentOut],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document for ingestion",
)
async def upload_document(user: CurrentUser, db: DbSession, file: UploadFile = File(...)):
    """
    Upload a .txt / .md / .faq file. It is chunked and indexed immediately, and
    becomes searchable through `POST /ask`.

    Uploading the same bytes twice returns the existing document rather than
    indexing a duplicate.
    """
    api_limiter.check(f"upload:{user.id}")
    settings = get_settings()

    try:
        raw = await read_limited(file, settings.max_upload_bytes)
        document = ingest(db, user.id, file.filename or "untitled", raw)
    except IngestionError as e:
        # One exception type carrying its own status code keeps the route thin.
        raise HTTPException(e.status_code, e.message) from None
    finally:
        await file.close()

    return ok(
        document,
        f"Ingested '{document.filename}' into {document.chunk_count} chunk(s)",
    )


@router.get("", response_model=ApiResponse[DocumentList])
def list_documents(user: CurrentUser, db: DbSession):
    """List only the caller's documents."""
    documents = list(
        db.execute(
            select(Document)
            .where(Document.user_id == user.id)
            .order_by(Document.created_at.desc())
        )
        .scalars()
        .all()
    )

    total_chunks = db.execute(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.user_id == user.id)
    ).scalar_one()

    return ok(
        DocumentList(
            total=len(documents),
            total_chunks=total_chunks,
            items=[DocumentOut.model_validate(d) for d in documents],
        ),
        f"{len(documents)} document(s)",
    )


@router.get("/{document_id}", response_model=ApiResponse[DocumentOut])
def get_document(document_id: int, user: CurrentUser, db: DbSession):
    document = db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user.id,      # authorization, not a filter
        )
    ).scalar_one_or_none()

    if document is None:
        # 404 rather than 403 on someone else's document: confirming that an
        # id exists but belongs to another user is itself a small leak.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    return ok(document)


@router.delete("/{document_id}", response_model=ApiResponse[None])
def remove_document(document_id: int, user: CurrentUser, db: DbSession):
    """Delete the document, its chunks, and the stored file."""
    if not delete_document(db, user.id, document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    return ok(message="Document deleted")
