from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from maiecho_py.internal.container import AppContainer

router = APIRouter(prefix="/collect", tags=["collector"])


class CollectRequest(BaseModel):
    keyword: str = ""
    game_id: int = 0


def _container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.container)


@router.post("")
async def trigger_collection(
    payload: CollectRequest, request: Request
) -> dict[str, object]:
    service = _container(request).collector_service
    if payload.game_id > 0:
        song = service.get_song_by_game_id(payload.game_id)
        if song is None:
            raise HTTPException(status_code=404, detail="未找到对应的歌曲")
        keywords = [f"{song.title} maimai"]
        if len(song.title) < 5 and song.artist:
            keywords.append(f"{song.title} {song.artist} maimai")
        for alias in song.aliases[:5]:
            if len(alias.alias) < 2:
                continue
            is_suitable = await service.check_alias_suitability(song, alias.alias)
            service.update_alias_suitability(alias.id, is_suitable)
            if is_suitable:
                keywords.append(f"{alias.alias} 舞萌 maimai 手元 谱面确认")
        queued = 0
        for keyword in keywords:
            if service.trigger_collection(keyword, song.id):
                queued += 1
        return {
            "message": "基于GameID的数据收集任务已启动",
            "keywords": keywords,
            "queued": queued,
        }

    if not payload.keyword:
        raise HTTPException(status_code=400, detail="必须提供 keyword 或 game_id")

    search_keyword = f"{payload.keyword} 舞萌 maimai 手元 谱面确认"
    queued = service.trigger_collection(search_keyword, None)
    return {
        "message": "数据收集任务已启动",
        "keyword": search_keyword,
        "queued": queued,
    }


@router.post("/backfill")
def backfill_collection(request: Request) -> dict[str, object]:
    queued = _container(request).collector_service.backfill_collection()
    return {"message": "回填数据收集任务已排队", "queued": queued}
