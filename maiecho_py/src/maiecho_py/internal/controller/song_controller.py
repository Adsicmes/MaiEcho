from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from maiecho_py.internal.container import AppContainer
from maiecho_py.internal.model import Song, SongFilter

router = APIRouter(prefix="/songs", tags=["songs"])


class SongAliasResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alias: str
    is_suitable: bool


class ChartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    difficulty: str
    level: str | None
    ds: float | None
    fit: float | None
    notes: str | None
    charter: str | None
    avg_achievement: float | None
    avg_dx: float | None
    std_dev: float | None
    sample_count: int | None


class SongResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    game_id: int | None
    title: str
    artist: str | None
    genre: str | None
    bpm: float | None
    release_date: str | None
    version: str | None
    type: str | None
    is_new: bool
    cover_url: str | None
    last_scraped: str | None
    charts: list[ChartResponse] = Field(default_factory=list)
    aliases: list[SongAliasResponse] = Field(default_factory=list)


class SongListResponse(BaseModel):
    total: int
    items: list[SongResponse]


class CreateSongRequest(BaseModel):
    game_id: int | None = None
    title: str
    artist: str | None = None
    genre: str | None = None
    bpm: float | None = None
    release_date: str | None = None
    version: str | None = None
    type: str | None = None
    is_new: bool = False
    cover_url: str | None = None


class MessageResponse(BaseModel):
    message: str
    count: int | None = None


def _container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.container)


@router.get("", response_model=SongListResponse)
def list_songs(
    request: Request,
    version: str = "",
    min_ds: float = 0.0,
    max_ds: float = 0.0,
    type: str = "",
    genre: str = "",
    is_new: bool | None = None,
    keyword: str = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
) -> SongListResponse:
    song_filter = SongFilter(
        version=version,
        min_ds=min_ds,
        max_ds=max_ds,
        type=type,
        genre=genre,
        is_new=is_new,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    songs, total = _container(request).song_service.get_songs(song_filter)
    return SongListResponse(
        total=total,
        items=[SongResponse.model_validate(song) for song in songs],
    )


@router.get("/{song_id}", response_model=SongResponse)
def get_song(song_id: int, request: Request) -> SongResponse:
    song = _container(request).song_service.get_song_by_game_id(song_id)
    if song is None:
        raise HTTPException(status_code=404, detail="未找到对应的歌曲")
    return SongResponse.model_validate(song)


@router.post("", response_model=SongResponse)
def create_song(payload: CreateSongRequest, request: Request) -> SongResponse:
    song = Song(**payload.model_dump())
    created = _container(request).song_service.create_song(song)
    return SongResponse.model_validate(created)


@router.post("/sync", response_model=MessageResponse)
async def sync_songs(request: Request) -> MessageResponse:
    count = await _container(request).song_service.sync_from_divingfish()
    return MessageResponse(message="同步完成", count=count)


@router.post("/aliases/refresh", response_model=MessageResponse)
async def refresh_aliases(request: Request) -> MessageResponse:
    count = await _container(request).song_service.refresh_aliases()
    return MessageResponse(message="别名刷新成功", count=count)
