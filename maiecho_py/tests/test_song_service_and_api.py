from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

from maiecho_py.app import create_app
from maiecho_py.internal.container import AppContainer
from maiecho_py.internal.llm.client import LLMClient
from maiecho_py.internal.model import Chart, Song
from maiecho_py.internal.provider.yuzuchan.client import AliasItem
from maiecho_py.internal.provider.registry import ProviderRegistry
from maiecho_py.internal.scheduler.scheduler import AppScheduler
from maiecho_py.internal.service.services import AnalysisService, CollectorService
from maiecho_py.internal.storage.database import build_database
from maiecho_py.internal.status.status import StatusService
import maiecho_py.app as app_module
import maiecho_py.internal.storage as storage
from maiecho_py.internal.service.services import SongService


class FakeDivingFishClient:
    async def fetch_songs(self) -> list[Song]:
        return [
            Song(
                game_id=114514,
                title="Sync Song",
                artist="Composer",
                type="DX",
                charts=[Chart(difficulty="Master", level="14", ds=14.0, fit=14.2)],
            )
        ]

    async def close(self) -> None:
        return None


class FakeYuzuChanClient:
    async def fetch_alias_by_song_id(self, song_id: int) -> AliasItem | None:
        if song_id == 114514:
            return AliasItem(
                song_id=song_id, name="Sync Song", aliases=["同步歌", "测试别名"]
            )
        return None

    async def close(self) -> None:
        return None


@dataclass(slots=True)
class FakeProviders:
    divingfish: FakeDivingFishClient
    yuzuchan: FakeYuzuChanClient

    async def close(self) -> None:
        return None


@dataclass(slots=True)
class FakeScheduler:
    def start(self) -> None:
        return None

    def shutdown(self, wait: bool = False) -> None:
        _ = wait
        return None

    async def close_collectors(self) -> None:
        return None


@dataclass(slots=True)
class FakeLLM:
    async def close(self) -> None:
        return None


@dataclass(slots=True)
class FakeStatusService:
    def get_system_status(self) -> object:
        raise AssertionError("status endpoint not used in this test")


def test_song_sync_and_alias_refresh_api(tmp_path: Path) -> None:
    database = build_database(str(tmp_path / "api.db"))
    repository = storage.StorageRepository(database)
    providers = FakeProviders(FakeDivingFishClient(), FakeYuzuChanClient())
    song_service = SongService(
        storage=repository,
        divingfish=providers.divingfish,
        yuzuchan=providers.yuzuchan,
    )
    analysis_service = AnalysisService(storage=repository)
    collector_service = CollectorService(
        scheduler=cast(AppScheduler, FakeScheduler()),
        storage=repository,
        song_service=song_service,
    )

    fake_container = AppContainer(
        config=object(),
        prompts=object(),
        database=database,
        providers=cast(ProviderRegistry, providers),
        llm=cast(LLMClient, FakeLLM()),
        scheduler=cast(AppScheduler, FakeScheduler()),
        status_service=cast(StatusService, FakeStatusService()),
        storage=repository,
        song_service=song_service,
        analysis_service=analysis_service,
        collector_service=collector_service,
    )

    original = app_module.build_app_container
    app_module.build_app_container = lambda: fake_container
    try:
        with TestClient(create_app()) as client:
            sync_response = client.post("/api/v1/songs/sync")
            assert sync_response.status_code == 200
            assert sync_response.json() == {"message": "同步完成", "count": 1}

            list_response = client.get("/api/v1/songs")
            assert list_response.status_code == 200
            assert list_response.json()["total"] == 1
            assert list_response.json()["items"][0]["title"] == "Sync Song"

            detail_response = client.get("/api/v1/songs/114514")
            assert detail_response.status_code == 200
            assert detail_response.json()["game_id"] == 114514

            alias_response = client.post("/api/v1/songs/aliases/refresh")
            assert alias_response.status_code == 200
            assert alias_response.json() == {"message": "别名刷新成功", "count": 1}

            detail_after_alias = client.get("/api/v1/songs/114514")
            assert detail_after_alias.status_code == 200
            aliases = detail_after_alias.json()["aliases"]
            assert [item["alias"] for item in aliases] == ["同步歌", "测试别名"]
    finally:
        app_module.build_app_container = original
        database.dispose()
