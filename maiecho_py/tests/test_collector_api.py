from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

import maiecho_py.app as app_module
import maiecho_py.internal.storage as storage
from maiecho_py.app import create_app
from maiecho_py.internal.collector.base import Collector
from maiecho_py.internal.container import AppContainer
from maiecho_py.internal.llm.client import LLMClient
from maiecho_py.internal.model import Comment, Song
from maiecho_py.internal.provider.registry import ProviderRegistry
from maiecho_py.internal.scheduler.scheduler import AppScheduler
from maiecho_py.internal.service.services import (
    AnalysisService,
    CollectorService,
    SongService,
)
from maiecho_py.internal.status.status import StatusService
from maiecho_py.internal.storage.database import build_database


class FakeCollector(Collector):
    source_name = "bilibili"

    def __init__(self, repository: storage.StorageRepository) -> None:
        self.repository = repository

    async def collect(self, keyword: str, song_id: int | None = None) -> None:
        self.repository.create_comment(
            Comment(
                song_id=song_id,
                source="Bilibili",
                source_title=keyword,
                external_id=f"{keyword}-{song_id}",
                content="采集到的评论",
                search_tag=keyword,
            )
        )

    async def close(self) -> None:
        return None


@dataclass(slots=True)
class FakeProviders:
    async def close(self) -> None:
        return None


class FakeSongProvider:
    async def fetch_songs(self) -> list[Song]:
        return []


class FakeAliasProvider:
    async def fetch_alias_by_song_id(self, song_id: int) -> None:
        _ = song_id
        return None


@dataclass(slots=True)
class FakeLLM:
    async def close(self) -> None:
        return None


def test_collect_and_backfill_api_queue_and_execute(tmp_path: Path) -> None:
    database = build_database(str(tmp_path / "collect-api.db"))
    repository = storage.StorageRepository(database)
    song = repository.create_song(Song(game_id=999, title="Queue Song"))
    song_service = SongService(
        storage=repository,
        divingfish=FakeSongProvider(),
        yuzuchan=FakeAliasProvider(),
    )
    scheduler = AppScheduler(collectors=[FakeCollector(repository)], storage=repository)
    collector_service = CollectorService(
        scheduler=scheduler,
        storage=repository,
        song_service=song_service,
    )
    fake_container = AppContainer(
        config=object(),
        prompts=object(),
        database=database,
        providers=cast(ProviderRegistry, FakeProviders()),
        llm=cast(LLMClient, FakeLLM()),
        scheduler=scheduler,
        status_service=cast(StatusService, object()),
        storage=repository,
        song_service=song_service,
        analysis_service=AnalysisService(storage=repository),
        collector_service=collector_service,
    )

    original = app_module.build_app_container
    app_module.build_app_container = lambda: fake_container
    try:
        with TestClient(create_app()) as client:
            response = client.post("/api/v1/collect", json={"game_id": 999})
            assert response.status_code == 200
            assert response.json()["queued"] >= 1
            assert collector_service.wait_until_idle(timeout=3.0)
            comments = repository.get_comments_by_song_id(song.id)
            assert len(comments) >= 1

            response = client.post("/api/v1/collect/backfill")
            assert response.status_code == 200
            assert response.json()["queued"] == 0
    finally:
        app_module.build_app_container = original
        scheduler.shutdown(wait=True)
        database.dispose()
