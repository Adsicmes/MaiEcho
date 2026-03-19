from __future__ import annotations

import time
from pathlib import Path
from typing import cast

import maiecho_py.internal.storage as storage
from pydantic import BaseModel
from maiecho_py.internal.agent.mapper import CommentMapper
from maiecho_py.internal.collector.base import Collector
from maiecho_py.internal.config.loader import load_prompt_config
from maiecho_py.internal.llm.client import LLMClient
from maiecho_py.internal.model import Comment, Song
from maiecho_py.internal.scheduler.scheduler import AppScheduler
from maiecho_py.internal.service.services import (
    AnalysisService,
    CollectorService,
    SongService,
)
from maiecho_py.internal.storage.database import build_database


class FakeDiscoveryCollector(Collector):
    source_name = "bilibili_discovery"

    def __init__(self, repository: storage.StorageRepository) -> None:
        self.repository = repository

    async def collect(self, keyword: str, song_id: int | None = None) -> None:
        _ = keyword
        _ = song_id
        self.repository.create_comment(
            Comment(
                source="Bilibili_Discovery",
                source_title="NS Master 手元",
                external_id="discovery-video",
                content="这谱有纵连而且尾杀，感觉有点诈称",
                search_tag="maimai",
            )
        )

    async def close(self) -> None:
        return None


class FakeSongProvider:
    async def fetch_songs(self) -> list[Song]:
        return []


class FakeAliasProvider:
    async def fetch_alias_by_song_id(self, song_id: int) -> None:
        _ = song_id
        return None


class FakeLLM:
    async def close(self) -> None:
        return None

    async def structured(
        self, system_prompt: str, user_prompt: str, model: type[BaseModel]
    ) -> BaseModel:
        if "是否指的是特定歌曲" in system_prompt:
            return model.model_validate({"decision": "YES", "reason": "matched"})
        if "严格的音游评论数据清洗员" in system_prompt:
            cleaned = []
            for line in user_prompt.splitlines():
                if ". " in line:
                    cleaned.append(line.split(". ", 1)[1])
            return model.model_validate({"comments": cleaned})
        if "舞萌（maimai）顾问" in system_prompt or "舞萌(maimai)顾问" in system_prompt:
            return model.model_validate(
                {
                    "summary": "advisor summary",
                    "rating_advice": "advisor advice",
                    "difficulty_analysis": "advisor difficulty",
                }
            )
        return model.model_validate(
            {
                "difficulty_tags": ["诈称"],
                "key_patterns": ["纵连"],
                "pros": ["手感好"],
                "cons": ["尾杀"],
                "sentiment": "Positive",
                "reasoning": "reasoning",
            }
        )


def test_scheduler_periodically_runs_discovery_mapper_and_analysis(
    tmp_path: Path,
) -> None:
    database = build_database(str(tmp_path / "scheduler.db"))
    repository = storage.StorageRepository(database)
    song = repository.create_song(Song(game_id=4321, title="Night Sky"))
    repository.save_song_aliases(song.id, ["NS"])

    scheduler = AppScheduler(
        collectors=[FakeDiscoveryCollector(repository)],
        storage=repository,
    )
    song_service = SongService(
        storage=repository,
        divingfish=FakeSongProvider(),
        yuzuchan=FakeAliasProvider(),
    )
    collector_service = CollectorService(
        scheduler=scheduler,
        storage=repository,
        song_service=song_service,
        mapper=CommentMapper(
            repository,
            cast(LLMClient, FakeLLM()),
            load_prompt_config(),
        ),
    )
    analysis_service = AnalysisService.with_pipeline(
        storage=repository,
        llm=cast(LLMClient, FakeLLM()),
        prompts=load_prompt_config(),
    )

    scheduler.add_periodic_job(
        name="discovery",
        interval_seconds=0.2,
        callback=lambda: collector_service.trigger_discovery(["maimai"]),
    )
    scheduler.add_periodic_job(
        name="mapper",
        interval_seconds=0.2,
        callback=collector_service.map_comments_to_songs,
    )
    scheduler.add_periodic_job(
        name="analysis",
        interval_seconds=0.2,
        callback=analysis_service.analyze_pending_songs,
    )

    scheduler.start()
    time.sleep(1.2)
    scheduler.shutdown(wait=True)

    linked_comments = repository.get_comments_by_song_id(song.id)
    assert len(linked_comments) >= 1
    result = repository.get_analysis_result_by_song_id(song.id)
    assert result is not None
    assert result.summary == "advisor summary"
    database.dispose()
