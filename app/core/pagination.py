from typing import TypeVar, Generic, List
from fastapi import Query, Depends
from pydantic import BaseModel, Field, computed_field

T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int           # ← User input: which page
    limit: int
    
    @computed_field
    @property
    def pages(self) -> int:
        """Total number of pages."""
        return (self.total + self.limit - 1) // self.limit

    @computed_field
    @property
    def has_next(self) -> bool:
        return (self.page * self.limit) < self.total

    @computed_field
    @property
    def has_prev(self) -> bool:
        return self.page > 1


class PaginationParams(BaseModel):
    """Page-based pagination."""
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    limit: int = Field(default=20, ge=1, le=100, description="Items per page")


def paginate(items: List, params: PaginationParams) -> Page:
    """Convert page number to offset."""
    skip = (params.page - 1) * params.limit  # page=1 → skip=0, page=2 → skip=20
    return Page(
        items=items[skip : skip + params.limit],
        total=len(items),
        page=params.page,
        limit=params.limit,
    )