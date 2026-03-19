from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

import maiecho_py.app as app_module
import maiecho_py.internal.storage as storage
from maiecho_py.app import create_app
from maiecho_py.internal.container import AppContainer
from maiecho_py.internal.llm.client import LLMClient
from maiecho_py.internal.model import Song
from maiecho_py.internal.provider.registry import ProviderRegistry
from maiecho_py.internal.scheduler.scheduler import AppScheduler
from maiecho_py.internal.service.services import (
    AnalysisService,
    CollectorService,
    SongService,
)
from maiecho_py.internal.status.status import StatusService
from maiecho_py.internal.storage.database import build_database


class FakeSongProvider:
    async def fetch_songs(self) -> list[Song]:
        return []


class FakeAliasProvider:
    async def fetch_alias_by_song_id(self, song_id: int) -> None:
        _ = song_id
        return None


@dataclass(slots=True)
class FakeProviders:
    async def close(self) -> None:
        return None


@dataclass(slots=True)
class FakeLLM:
    async def close(self) -> None:
        return None


@dataclass(slots=True)
class FakeScheduler:
    def add_task(self, task: object) -> bool:
        _ = task
        return True

    def wait_until_idle(self, timeout: float = 5.0) -> bool:
        _ = timeout
        return True

    def queue_size(self) -> int:
        return 0

    def active_task_count(self) -> int:
        return 0

    def periodic_job_names(self) -> list[str]:
        return []

    def recent_task_records(self) -> list[dict[str, str]]:
        return []

    def collector_health(self) -> list[dict[str, str]]:
        return []

    def start(self) -> None:
        return None

    def shutdown(self, wait: bool = False) -> None:
        _ = wait
        return None

    async def close_collectors(self) -> None:
        return None


class FakeCollectorService(CollectorService):
    async def check_alias_suitability(self, song: Song, alias: str) -> bool:
        return alias != "NS"


def test_collect_updates_alias_suitability_flag(tmp_path: Path) -> None:
    database = build_database(str(tmp_path / "alias.db"))
    repository = storage.StorageRepository(database)
    song = repository.create_song(Song(game_id=7777, title="Night Sky"))
    repository.save_song_aliases(song.id, ["NS", "NightSky"])
    song_service = SongService(
        storage=repository,
        divingfish=FakeSongProvider(),
        yuzuchan=FakeAliasProvider(),
    )
    collector_service = FakeCollectorService(
        scheduler=cast(AppScheduler, FakeScheduler()),
        storage=repository,
        song_service=song_service,
    )
    fake_container = AppContainer(
        config=object(),
        prompts=object(),
        database=database,
        providers=cast(ProviderRegistry, FakeProviders()),
        llm=cast(LLMClient, FakeLLM()),
        scheduler=cast(AppScheduler, FakeScheduler()),
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
            response = client.post("/api/v1/collect", json={"game_id": 7777})
            assert response.status_code == 200
            payload = response.json()
            assert all("NS 舞萌" not in keyword for keyword in payload["keywords"])
            assert any("NightSky 舞萌" in keyword for keyword in payload["keywords"])
        refreshed = repository.get_song(song.id)
        assert refreshed is not None
        alias_flags = {alias.alias: alias.is_suitable for alias in refreshed.aliases}
        assert alias_flags["NS"] is False
        assert alias_flags["NightSky"] is True
    finally:
        app_module.build_app_container = original
        database.dispose()


def test_collect_short_title_adds_artist_keyword(tmp_path: Path) -> None:
    database = build_database(str(tmp_path / "short-title.db"))
    repository = storage.StorageRepository(database)
    repository.create_song(Song(game_id=8888, title="Lime", artist="Artist"))
    song_service = SongService(
        storage=repository,
        divingfish=FakeSongProvider(),
        yuzuchan=FakeAliasProvider(),
    )
    collector_service = FakeCollectorService(
        scheduler=cast(AppScheduler, FakeScheduler()),
        storage=repository,
        song_service=song_service,
    )
    fake_container = AppContainer(
        config=object(),
        prompts=object(),
        database=database,
        providers=cast(ProviderRegistry, FakeProviders()),
        llm=cast(LLMClient, FakeLLM()),
        scheduler=cast(AppScheduler, FakeScheduler()),
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
            response = client.post("/api/v1/collect", json={"game_id": 8888})
            assert response.status_code == 200
            keywords = response.json()["keywords"]
            assert "Lime maimai" in keywords
            assert "Lime Artist maimai" in keywords
    finally:
        app_module.build_app_container = original
        database.dispose()
