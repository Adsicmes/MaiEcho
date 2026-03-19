from __future__ import annotations

from pathlib import Path
import json
from typing import cast
from dataclasses import dataclass

from fastapi.testclient import TestClient
from pydantic import BaseModel

import maiecho_py.app as app_module
import maiecho_py.internal.storage as storage
from maiecho_py.app import create_app
from maiecho_py.internal.config.loader import load_prompt_config
from maiecho_py.internal.container import AppContainer
from maiecho_py.internal.llm.client import LLMClient
from maiecho_py.internal.model import AnalysisResult, Chart, Comment, Song
from maiecho_py.internal.provider.registry import ProviderRegistry
from maiecho_py.internal.scheduler.scheduler import AppScheduler
from maiecho_py.internal.service.services import (
    AnalysisService,
    CollectorService,
    SongService,
)
from maiecho_py.internal.status.status import StatusService
from maiecho_py.internal.storage.database import build_database


class FakeDivingFishClient:
    async def fetch_songs(self) -> list[Song]:
        return []

    async def close(self) -> None:
        return None


class FakeYuzuChanClient:
    async def fetch_alias_by_song_id(self, song_id: int) -> None:
        _ = song_id
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

    async def structured(
        self, system_prompt: str, user_prompt: str, model: type[BaseModel]
    ) -> BaseModel:
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


@dataclass(slots=True)
class FakeStatus:
    def get_system_status(self) -> object:
        return {}


def test_analysis_get_returns_aggregated_results(tmp_path: Path) -> None:
    database = build_database(str(tmp_path / "analysis.db"))
    repository = storage.StorageRepository(database)
    song = repository.create_song(
        Song(
            game_id=2468,
            title="Analysis Song",
            charts=[Chart(difficulty="Master", level="14", ds=14.0, fit=14.3)],
        )
    )
    repository.create_analysis_result(
        AnalysisResult(
            target_type="song",
            target_id=song.id,
            summary="song summary",
            rating_advice="song advice",
            difficulty_analysis="song difficulty",
        )
    )
    persisted_song = repository.get_song(song.id)
    assert persisted_song is not None
    chart_id = persisted_song.charts[0].id
    repository.create_analysis_result(
        AnalysisResult(
            target_type="chart",
            target_id=chart_id,
            summary="chart summary",
            rating_advice="chart advice",
            difficulty_analysis="chart difficulty",
        )
    )

    song_service = SongService(
        storage=repository,
        divingfish=FakeDivingFishClient(),
        yuzuchan=FakeYuzuChanClient(),
    )
    analysis_service = AnalysisService(storage=repository)
    collector_service = CollectorService(
        scheduler=cast(AppScheduler, FakeScheduler()),
        storage=repository,
        song_service=song_service,
    )
    providers = FakeProviders(FakeDivingFishClient(), FakeYuzuChanClient())
    fake_container = AppContainer(
        config=object(),
        prompts=object(),
        database=database,
        providers=cast(ProviderRegistry, providers),
        llm=cast(LLMClient, FakeLLM()),
        scheduler=cast(AppScheduler, FakeScheduler()),
        status_service=cast(StatusService, FakeStatus()),
        storage=repository,
        song_service=song_service,
        analysis_service=analysis_service,
        collector_service=collector_service,
    )

    original = app_module.build_app_container
    app_module.build_app_container = lambda: fake_container
    try:
        with TestClient(create_app()) as client:
            response = client.get("/api/v1/analysis/songs/2468")
            assert response.status_code == 200
            payload = response.json()
            assert payload["song_result"]["summary"] == "song summary"
            assert payload["chart_results"][0]["summary"] == "chart summary"
    finally:
        app_module.build_app_container = original
        database.dispose()


def test_analysis_post_generates_results(tmp_path: Path) -> None:
    database = build_database(str(tmp_path / "analysis-post.db"))
    repository = storage.StorageRepository(database)
    prompts = load_prompt_config()
    song = repository.create_song(
        Song(
            game_id=8642,
            title="Generated Song",
            charts=[Chart(difficulty="Master", level="14", ds=14.0, fit=14.4)],
        )
    )
    repository.create_comment(
        Comment(
            song_id=song.id,
            source_title="Generated Song Master 手元",
            content="这谱有纵连而且尾杀，感觉有点诈称",
        )
    )

    song_service = SongService(
        storage=repository,
        divingfish=FakeDivingFishClient(),
        yuzuchan=FakeYuzuChanClient(),
    )
    analysis_service = AnalysisService.with_pipeline(
        storage=repository,
        llm=cast(LLMClient, FakeLLM()),
        prompts=prompts,
    )
    collector_service = CollectorService(
        scheduler=cast(AppScheduler, FakeScheduler()),
        storage=repository,
        song_service=song_service,
    )
    providers = FakeProviders(FakeDivingFishClient(), FakeYuzuChanClient())
    fake_container = AppContainer(
        config=object(),
        prompts=prompts,
        database=database,
        providers=cast(ProviderRegistry, providers),
        llm=cast(LLMClient, FakeLLM()),
        scheduler=cast(AppScheduler, FakeScheduler()),
        status_service=cast(StatusService, FakeStatus()),
        storage=repository,
        song_service=song_service,
        analysis_service=analysis_service,
        collector_service=collector_service,
    )

    original = app_module.build_app_container
    app_module.build_app_container = lambda: fake_container
    try:
        with TestClient(create_app()) as client:
            post_response = client.post("/api/v1/analysis/songs/8642")
            assert post_response.status_code == 200
            assert post_response.json() == {"message": "分析完成", "generated": True}

            get_response = client.get("/api/v1/analysis/songs/8642")
            assert get_response.status_code == 200
            payload = get_response.json()
            assert payload["song_result"]["summary"] == "advisor summary"
            assert payload["chart_results"][0]["summary"] == "advisor summary"
    finally:
        app_module.build_app_container = original
        database.dispose()


def test_analysis_post_ignores_noise_and_unofficial_chart(tmp_path: Path) -> None:
    database = build_database(str(tmp_path / "analysis-noise.db"))
    repository = storage.StorageRepository(database)
    prompts = load_prompt_config()
    song = repository.create_song(
        Song(
            game_id=9753,
            title="Noise Song",
            charts=[Chart(difficulty="Master", level="14", ds=14.0, fit=14.1)],
        )
    )
    repository.create_comment(
        Comment(
            song_id=song.id, source_title="Noise Song 自制谱", content="这谱有点意思"
        )
    )
    repository.create_comment(
        Comment(song_id=song.id, source_title="Noise Song Master 手元", content="第一")
    )

    song_service = SongService(
        storage=repository,
        divingfish=FakeDivingFishClient(),
        yuzuchan=FakeYuzuChanClient(),
    )
    analysis_service = AnalysisService.with_pipeline(
        storage=repository,
        llm=cast(LLMClient, FakeLLM()),
        prompts=prompts,
    )
    collector_service = CollectorService(
        scheduler=cast(AppScheduler, FakeScheduler()),
        storage=repository,
        song_service=song_service,
    )
    providers = FakeProviders(FakeDivingFishClient(), FakeYuzuChanClient())
    fake_container = AppContainer(
        config=object(),
        prompts=prompts,
        database=database,
        providers=cast(ProviderRegistry, providers),
        llm=cast(LLMClient, FakeLLM()),
        scheduler=cast(AppScheduler, FakeScheduler()),
        status_service=cast(StatusService, FakeStatus()),
        storage=repository,
        song_service=song_service,
        analysis_service=analysis_service,
        collector_service=collector_service,
    )

    original = app_module.build_app_container
    app_module.build_app_container = lambda: fake_container
    try:
        with TestClient(create_app()) as client:
            response = client.post("/api/v1/analysis/songs/9753")
            assert response.status_code == 200
            assert response.json() == {"message": "无可分析评论", "generated": False}
    finally:
        app_module.build_app_container = original
        database.dispose()


def test_analysis_post_keeps_valid_short_terms(tmp_path: Path) -> None:
    database = build_database(str(tmp_path / "analysis-short.db"))
    repository = storage.StorageRepository(database)
    prompts = load_prompt_config()
    song = repository.create_song(
        Song(
            game_id=1357,
            title="Short Song",
            charts=[Chart(difficulty="Master", level="14", ds=14.0, fit=14.1)],
        )
    )
    repository.create_comment(
        Comment(song_id=song.id, source_title="Short Song Master 手元", content="AP")
    )

    song_service = SongService(
        storage=repository,
        divingfish=FakeDivingFishClient(),
        yuzuchan=FakeYuzuChanClient(),
    )
    analysis_service = AnalysisService.with_pipeline(
        storage=repository,
        llm=cast(LLMClient, FakeLLM()),
        prompts=prompts,
    )
    collector_service = CollectorService(
        scheduler=cast(AppScheduler, FakeScheduler()),
        storage=repository,
        song_service=song_service,
    )
    providers = FakeProviders(FakeDivingFishClient(), FakeYuzuChanClient())
    fake_container = AppContainer(
        config=object(),
        prompts=prompts,
        database=database,
        providers=cast(ProviderRegistry, providers),
        llm=cast(LLMClient, FakeLLM()),
        scheduler=cast(AppScheduler, FakeScheduler()),
        status_service=cast(StatusService, FakeStatus()),
        storage=repository,
        song_service=song_service,
        analysis_service=analysis_service,
        collector_service=collector_service,
    )

    original = app_module.build_app_container
    app_module.build_app_container = lambda: fake_container
    try:
        with TestClient(create_app()) as client:
            response = client.post("/api/v1/analysis/songs/1357")
            assert response.status_code == 200
            assert response.json() == {"message": "分析完成", "generated": True}
    finally:
        app_module.build_app_container = original
        database.dispose()


def test_analysis_post_uses_map_reduce_for_song_level(tmp_path: Path) -> None:
    @dataclass(slots=True)
    class ChunkAwareLLM:
        async def close(self) -> None:
            return None

        async def structured(
            self, system_prompt: str, user_prompt: str, model: type[BaseModel]
        ) -> BaseModel:
            if "严格的音游评论数据清洗员" in system_prompt:
                cleaned = []
                for line in user_prompt.splitlines():
                    if ". " in line:
                        cleaned.append(line.split(". ", 1)[1])
                return model.model_validate({"comments": cleaned})
            if (
                "舞萌（maimai）顾问" in system_prompt
                or "舞萌(maimai)顾问" in system_prompt
            ):
                return model.model_validate(
                    {
                        "summary": "advisor summary",
                        "rating_advice": "advisor advice",
                        "difficulty_analysis": "advisor difficulty",
                    }
                )
            if "评论 54" in user_prompt:
                return model.model_validate(
                    {
                        "difficulty_tags": ["诈称"],
                        "key_patterns": ["尾杀"],
                        "pros": ["手感好"],
                        "cons": ["后半难"],
                        "sentiment": "Negative",
                        "version_analysis": "chunk-2",
                        "reasoning": "reasoning-2",
                    }
                )
            return model.model_validate(
                {
                    "difficulty_tags": ["越级"],
                    "key_patterns": ["纵连"],
                    "pros": ["配置明确"],
                    "cons": ["前半难"],
                    "sentiment": "Positive",
                    "version_analysis": "chunk-1",
                    "reasoning": "reasoning-1",
                }
            )

    database = build_database(str(tmp_path / "analysis-map-reduce.db"))
    repository = storage.StorageRepository(database)
    prompts = load_prompt_config()
    song = repository.create_song(
        Song(
            game_id=24680,
            title="Chunk Song",
            charts=[Chart(difficulty="Master", level="14", ds=14.0, fit=14.2)],
        )
    )
    for index in range(55):
        repository.create_comment(
            Comment(
                song_id=song.id,
                source_title="Chunk Song Master 手元",
                content=f"评论 {index} 这谱有纵连和尾杀，感觉有点诈称",
            )
        )

    song_service = SongService(
        storage=repository,
        divingfish=FakeDivingFishClient(),
        yuzuchan=FakeYuzuChanClient(),
    )
    analysis_service = AnalysisService.with_pipeline(
        storage=repository,
        llm=cast(LLMClient, ChunkAwareLLM()),
        prompts=prompts,
    )
    collector_service = CollectorService(
        scheduler=cast(AppScheduler, FakeScheduler()),
        storage=repository,
        song_service=song_service,
    )
    providers = FakeProviders(FakeDivingFishClient(), FakeYuzuChanClient())
    fake_container = AppContainer(
        config=object(),
        prompts=prompts,
        database=database,
        providers=cast(ProviderRegistry, providers),
        llm=cast(LLMClient, ChunkAwareLLM()),
        scheduler=cast(AppScheduler, FakeScheduler()),
        status_service=cast(StatusService, FakeStatus()),
        storage=repository,
        song_service=song_service,
        analysis_service=analysis_service,
        collector_service=collector_service,
    )

    original = app_module.build_app_container
    app_module.build_app_container = lambda: fake_container
    try:
        with TestClient(create_app()) as client:
            response = client.post("/api/v1/analysis/songs/24680")
            assert response.status_code == 200
            assert response.json() == {"message": "分析完成", "generated": True}

        result = repository.get_analysis_result_by_song_id(song.id)
        assert result is not None
        assert result.reasoning_log is not None
        assert "Chunk 0-50" in result.reasoning_log
        assert "Chunk 50-55" in result.reasoning_log
        payload = json.loads(result.payload_json or "{}")
        assert payload["chunk_count"] == 2
        assert payload["analyst"]["difficulty_tags"] == ["越级", "诈称"]
        assert payload["analyst"]["version_analysis"] == "chunk-1\nchunk-2"
    finally:
        app_module.build_app_container = original
        database.dispose()


def test_analysis_batch_runs_in_background(tmp_path: Path) -> None:
    database = build_database(str(tmp_path / "analysis-batch.db"))
    repository = storage.StorageRepository(database)
    prompts = load_prompt_config()
    for game_id in [2001, 2002]:
        song = repository.create_song(
            Song(
                game_id=game_id,
                title=f"Batch Song {game_id}",
                charts=[Chart(difficulty="Master", level="14", ds=14.0, fit=14.4)],
            )
        )
        repository.create_comment(
            Comment(
                song_id=song.id,
                source_title=f"Batch Song {game_id} Master 手元",
                content="这谱有纵连而且尾杀，感觉有点诈称",
            )
        )

    song_service = SongService(
        storage=repository,
        divingfish=FakeDivingFishClient(),
        yuzuchan=FakeYuzuChanClient(),
    )
    analysis_service = AnalysisService.with_pipeline(
        storage=repository,
        llm=cast(LLMClient, FakeLLM()),
        prompts=prompts,
    )
    collector_service = CollectorService(
        scheduler=cast(AppScheduler, FakeScheduler()),
        storage=repository,
        song_service=song_service,
    )
    providers = FakeProviders(FakeDivingFishClient(), FakeYuzuChanClient())
    fake_container = AppContainer(
        config=object(),
        prompts=prompts,
        database=database,
        providers=cast(ProviderRegistry, providers),
        llm=cast(LLMClient, FakeLLM()),
        scheduler=cast(AppScheduler, FakeScheduler()),
        status_service=cast(StatusService, FakeStatus()),
        storage=repository,
        song_service=song_service,
        analysis_service=analysis_service,
        collector_service=collector_service,
    )

    original = app_module.build_app_container
    app_module.build_app_container = lambda: fake_container
    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/api/v1/analysis/batch", json={"game_ids": [2001, 2002]}
            )
            assert response.status_code == 200
            assert response.json() == {"message": "批量分析任务已在后台启动"}

        song_one = repository.get_song_by_game_id(2001)
        song_two = repository.get_song_by_game_id(2002)
        assert song_one is not None and song_two is not None
        assert repository.get_analysis_result_by_song_id(song_one.id) is not None
        assert repository.get_analysis_result_by_song_id(song_two.id) is not None
    finally:
        app_module.build_app_container = original
        database.dispose()


def test_analysis_merge_prefers_majority_sentiment(tmp_path: Path) -> None:
    @dataclass(slots=True)
    class SentimentLLM:
        async def close(self) -> None:
            return None

        async def structured(
            self, system_prompt: str, user_prompt: str, model: type[BaseModel]
        ) -> BaseModel:
            if "严格的音游评论数据清洗员" in system_prompt:
                cleaned = []
                for line in user_prompt.splitlines():
                    if ". " in line:
                        cleaned.append(line.split(". ", 1)[1])
                return model.model_validate({"comments": cleaned})
            if (
                "舞萌（maimai）顾问" in system_prompt
                or "舞萌(maimai)顾问" in system_prompt
            ):
                return model.model_validate(
                    {
                        "summary": "advisor summary",
                        "rating_advice": "advisor advice",
                        "difficulty_analysis": "advisor difficulty",
                    }
                )
            if "评论 54" in user_prompt:
                return model.model_validate(
                    {
                        "difficulty_tags": ["诈称"],
                        "key_patterns": ["尾杀"],
                        "pros": [],
                        "cons": ["后半难"],
                        "sentiment": "Negative",
                        "version_analysis": "chunk-2",
                        "reasoning": "reasoning",
                    }
                )
            return model.model_validate(
                {
                    "difficulty_tags": ["越级"],
                    "key_patterns": ["纵连"],
                    "pros": ["配置明确"],
                    "cons": [],
                    "sentiment": "Positive",
                    "version_analysis": "chunk-1",
                    "reasoning": "reasoning",
                }
            )

    database = build_database(str(tmp_path / "analysis-sentiment.db"))
    repository = storage.StorageRepository(database)
    prompts = load_prompt_config()
    song = repository.create_song(
        Song(
            game_id=1111,
            title="Sentiment Song",
            charts=[Chart(difficulty="Master", level="14", ds=14.0, fit=14.2)],
        )
    )
    for index in range(55):
        repository.create_comment(
            Comment(
                song_id=song.id,
                source_title="Sentiment Song Master 手元",
                content=f"评论 {index} 这谱有纵连和尾杀",
            )
        )

    analysis_service = AnalysisService.with_pipeline(
        storage=repository,
        llm=cast(LLMClient, SentimentLLM()),
        prompts=prompts,
    )
    import asyncio

    assert asyncio.run(analysis_service.analyze_song_by_game_id(1111)) is True
    result = repository.get_analysis_result_by_song_id(song.id)
    assert result is not None
    payload = json.loads(result.payload_json or "{}")
    assert payload["analyst"]["sentiment"] == "Positive"
    database.dispose()
