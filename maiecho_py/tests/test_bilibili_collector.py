from __future__ import annotations

from pathlib import Path

import asyncio
import httpx
import pytest
from sqlalchemy import select

from maiecho_py.internal.collector.bilibili import BilibiliCollector
from maiecho_py.internal.model import Song, Video
import maiecho_py.internal.storage as storage
from maiecho_py.internal.storage.database import build_database


def test_bilibili_collector_saves_comments_and_videos(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/x/web-interface/search/all/v2"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "result": [
                            {
                                "result_type": "video",
                                "data": [
                                    {
                                        "bvid": "BV1xx411c7mD",
                                        "id": 123,
                                        "title": "<em>Sync Song</em> Master 手元",
                                        "description": "视频简介",
                                        "author": "Uploader",
                                    }
                                ],
                            }
                        ]
                    }
                },
            )
        if request.url.path.endswith("/x/v2/reply"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "replies": [
                            {
                                "rpid": "999",
                                "content": {"message": "这谱尾杀有点狠"},
                                "member": {"uname": "Commenter"},
                                "ctime": 1700000000,
                            }
                        ]
                    }
                },
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    database = build_database(str(tmp_path / "collector.db"))
    repository = storage.StorageRepository(database)
    song = repository.create_song(Song(game_id=555, title="Sync Song"))
    collector = BilibiliCollector(
        repository,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    asyncio.run(collector.collect("Sync Song maimai", song.id))
    asyncio.run(collector.close())

    comments = repository.get_comments_by_song_id(song.id)
    assert len(comments) == 2
    assert comments[0].source == "Bilibili"
    with database.session() as session:
        videos = list(session.scalars(select(Video)).all())
    assert len(videos) == 1
    assert videos[0].external_id == "BV1xx411c7mD"
    database.dispose()


def test_bilibili_collector_stops_on_empty_page(tmp_path: Path) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/x/web-interface/search/all/v2"):
            page = int(request.url.params.get("page", "1"))
            calls.append(page)
            if page == 1:
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "result": [
                                {
                                    "result_type": "video",
                                    "data": [],
                                }
                            ]
                        }
                    },
                )
        raise AssertionError(f"unexpected path: {request.url.path}")

    database = build_database(str(tmp_path / "empty.db"))
    repository = storage.StorageRepository(database)
    collector = BilibiliCollector(
        repository,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    asyncio.run(collector.collect("No Result", None))
    asyncio.run(collector.close())

    assert calls == [1]
    database.dispose()


def test_bilibili_collector_marks_ban_on_403(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/x/web-interface/search/all/v2"):
            return httpx.Response(403, json={})
        raise AssertionError(f"unexpected path: {request.url.path}")

    database = build_database(str(tmp_path / "ban.db"))
    repository = storage.StorageRepository(database)
    collector = BilibiliCollector(
        repository,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(collector.collect("Blocked", None))
    assert collector._is_banned is True
    asyncio.run(collector.close())
    database.dispose()


def test_bilibili_collector_marks_ban_on_api_risk_code(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/x/web-interface/search/all/v2"):
            return httpx.Response(200, json={"code": -352, "message": "风控校验失败"})
        raise AssertionError(f"unexpected path: {request.url.path}")

    database = build_database(str(tmp_path / "risk.db"))
    repository = storage.StorageRepository(database)
    collector = BilibiliCollector(
        repository,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(RuntimeError):
        asyncio.run(collector.collect("Risk", None))
    snapshot = collector.health_snapshot()
    assert snapshot["status"] == "banned"
    assert "风控校验失败" in str(snapshot["last_error"])
    asyncio.run(collector.close())
    database.dispose()
