import uuid

from pydantic import BaseModel


class SearchResultItem(BaseModel):
    id: uuid.UUID
    type: str  # "client" | "project" | "task"
    title: str
    subtitle: str | None = None
    url: str


class SearchResults(BaseModel):
    query: str
    results: list[SearchResultItem]
