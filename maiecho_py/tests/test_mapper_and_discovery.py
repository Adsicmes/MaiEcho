from __future__ import annotations

from pathlib import Path

import asyncio
import httpx
from sqlalchemy import select

import maiecho_py.internal.storage as storage
from maiecho_py.internal.agent.mapper import CommentMapper
from maiecho_py.internal.agent.relevance import RelevanceAnalyzer
from maiecho_py.internal.collector.discovery import BilibiliDiscoveryCollector
from maiecho_py.internal.config.loader import load_prompt_config
from maiecho_py.internal.llm.client import LLMClient
from maiecho_py.internal.model import Comment, Song, Video
from maiecho_py.internal.storage.database import build_database
from typing import cast


class FakeLLM:
    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        _ = system_prompt
        _ = user_prompt
        return "YES"


def test_comment_mapper_links_unmapped_comments_to_song(tmp_path: Path) -> None:
    database = build_database(str(tmp_path / "mapper.db"))
    repository = storage.StorageRepository(database)
    song = repository.create_song(Song(game_id=777, title="Night Sky"))
    repository.save_song_aliases(song.id, ["NS"])
    repository.create_comment(
        Comment(
            source="Bilibili_Discovery",
            source_title="NS Master 手元",
            content="这歌尾杀挺阴的",
        )
    )

    mapper = CommentMapper(repository, cast(LLMClient, FakeLLM()), load_prompt_config())
    updated = asyncio.run(mapper.map_comments_to_songs())

    assert updated == 1
    unmapped = repository.get_unmapped_comments()
    assert len(unmapped) == 0
    linked = repository.get_comments_by_song_id(song.id)
    assert len(linked) == 1
    database.dispose()


def test_comment_mapper_avoids_short_alias_false_positive(tmp_path: Path) -> None:
    database = build_database(str(tmp_path / "mapper-edge.db"))
    repository = storage.StorageRepository(database)
    song = repository.create_song(Song(game_id=778, title="Night Sky"))
    repository.save_song_aliases(song.id, ["NS"])
    repository.create_comment(
        Comment(
            source="Bilibili_Discovery",
            source_title="answers compilation",
            content="This answers chart looks fun",
        )
    )

    mapper = CommentMapper(repository, cast(LLMClient, FakeLLM()), load_prompt_config())
    updated = asyncio.run(mapper.map_comments_to_songs())

    assert updated == 0
    unmapped = repository.get_unmapped_comments()
    assert len(unmapped) == 1
    linked = repository.get_comments_by_song_id(song.id)
    assert len(linked) == 0
    database.dispose()


def test_comment_mapper_skips_ambiguous_candidates(tmp_path: Path) -> None:
    database = build_database(str(tmp_path / "mapper-ambiguous.db"))
    repository = storage.StorageRepository(database)
    first = repository.create_song(Song(game_id=1001, title="Alpha Song"))
    second = repository.create_song(Song(game_id=1002, title="Alpha Song"))
    repository.save_song_aliases(first.id, ["Alpha"])
    repository.save_song_aliases(second.id, ["Alpha"])
    repository.create_comment(
        Comment(
            source="Bilibili_Discovery",
            source_title="Alpha Master 手元",
            content="这歌有点难",
        )
    )

    mapper = CommentMapper(repository, cast(LLMClient, FakeLLM()), load_prompt_config())
    updated = asyncio.run(mapper.map_comments_to_songs())

    assert updated == 0
    assert len(repository.get_unmapped_comments()) == 1
    assert repository.get_comments_by_song_id(first.id) == []
    assert repository.get_comments_by_song_id(second.id) == []
    database.dispose()


def test_discovery_collector_saves_unmapped_content(tmp_path: Path) -> None:
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
                                        "bvid": "BVDiscovery",
                                        "title": "发现视频",
                                        "description": "发现描述",
                                        "author": "Discoverer",
                                    }
                                ],
                            }
                        ]
                    }
                },
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    database = build_database(str(tmp_path / "discovery.db"))
    repository = storage.StorageRepository(database)
    collector = BilibiliDiscoveryCollector(
        repository, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    asyncio.run(collector.collect("maimai"))
    asyncio.run(collector.close())

    unmapped = repository.get_unmapped_comments()
    assert len(unmapped) == 1
    assert unmapped[0].source == "Bilibili_Discovery"
    with database.session() as session:
        videos = list(session.scalars(select(Video)).all())
    assert len(videos) == 1
    assert videos[0].external_id == "BVDiscovery"
    database.dispose()


def test_relevance_rejects_generic_aliases_without_llm() -> None:
    analyzer = RelevanceAnalyzer(cast(LLMClient, FakeLLM()), load_prompt_config())

    import asyncio

    assert (
        asyncio.run(analyzer.check_alias_suitability("Night Sky", None, "dx")) is False
    )
    assert (
        asyncio.run(analyzer.check_alias_suitability("Night Sky", None, "123")) is False
    )
