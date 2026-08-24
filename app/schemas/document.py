"""Document DTOs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    size_bytes: int
    chunk_count: int
    created_at: datetime
    # stored_path and content_hash are deliberately absent: the client has no
    # use for a server filesystem path, and leaking it invites probing.


class DocumentList(BaseModel):
    total: int
    total_chunks: int
    items: list[DocumentOut]
