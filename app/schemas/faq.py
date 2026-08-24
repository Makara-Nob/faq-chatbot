"""Chat DTOs (same models as the single-file lesson version)."""

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=3, ge=1, le=10)


class SourceDoc(BaseModel):
    text: str
    score: float | None = None


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[SourceDoc]
    engine: str
    took_ms: int


class FaqItem(BaseModel):
    id: int
    question: str
    answer: str


class FaqList(BaseModel):
    total: int
    items: list[FaqItem]


class HealthResponse(BaseModel):
    status: str
    engine: str
    faq_count: int
