"""
Answering a question from a user's own uploaded documents.

The tenancy rule, stated once: every query here filters on user_id. A FAQ bot
that answers customer A from customer B's handbook is not a bug you recover
from, so the filter lives in one function rather than in every caller.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk
from app.schemas.faq import SourceDoc
from app.services import search


def user_chunk_count(db: Session, user_id: int) -> int:
    return len(
        db.execute(
            select(DocumentChunk.id).where(DocumentChunk.user_id == user_id)
        ).all()
    )


def answer_from_documents(
    db: Session, user_id: int, question: str, top_k: int
) -> tuple[str, list[SourceDoc]]:
    """
    Rank this user's chunks against the question.

    Loads the user's chunks and scores them in Python. That is honest for a
    corpus of this size (20 documents per user) and dishonest at scale - the
    real fix is pgvector or a vector database with a per-tenant filter, which
    is the same interface with a different body.
    """
    rows = db.execute(
        select(DocumentChunk.content, DocumentChunk.document_id)
        .where(DocumentChunk.user_id == user_id)
        .order_by(DocumentChunk.document_id, DocumentChunk.position)
    ).all()

    if not rows:
        return "You have not uploaded any documents yet.", []

    texts = [row.content for row in rows]
    ranked = search.rank(texts, question, top_k)

    if not ranked:
        return "I could not find anything about that in your documents.", []

    best_text = texts[ranked[0][0]]

    # The answer is the matching passage. A RAG engine would feed these same
    # passages to an LLM and return generated prose instead - same retrieval,
    # different last step.
    answer = _strip_qa_prefix(best_text)

    sources = [
        SourceDoc(text=texts[i], score=round(score, 3)) for i, score in ranked
    ]
    return answer, sources


def _strip_qa_prefix(chunk: str) -> str:
    """For 'Q: ...\\nA: ...' chunks, return just the answer."""
    for line in chunk.splitlines():
        if line.startswith("A:"):
            return line[2:].strip()
    return chunk.strip()
