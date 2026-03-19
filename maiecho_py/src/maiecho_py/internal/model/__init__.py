"""Database models."""

from pydantic import BaseModel, Field

from maiecho_py.internal.model.base import Base
from maiecho_py.internal.model.entities import (
    AnalysisResult,
    Chart,
    Comment,
    Song,
    SongAlias,
    Video,
)


class SongFilter(BaseModel):
    version: str = ""
    min_ds: float = 0.0
    max_ds: float = 0.0
    type: str = ""
    genre: str = ""
    is_new: bool | None = None
    keyword: str = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)


class SongListResponse(BaseModel):
    total: int
    items: list[dict[str, object]]


__all__ = [
    "AnalysisResult",
    "Base",
    "Chart",
    "Comment",
    "SongFilter",
    "SongListResponse",
    "Song",
    "SongAlias",
    "Video",
]
