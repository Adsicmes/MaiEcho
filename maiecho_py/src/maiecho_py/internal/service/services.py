from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from maiecho_py.internal.agent.mapper import CommentMapper
from maiecho_py.internal.agent.pipeline import AnalysisPipeline
from maiecho_py.internal.agent.relevance import RelevanceAnalyzer
from maiecho_py.internal.config.models import PromptConfig
from maiecho_py.internal.collector.base import CollectionTask
from maiecho_py.internal.model import AnalysisResult, Song, SongFilter
from maiecho_py.internal.scheduler.scheduler import AppScheduler
from maiecho_py.internal.storage import StorageRepository
from maiecho_py.internal.llm.client import LLMClient


class SongProvider(Protocol):
    async def fetch_songs(self) -> list[Song]: ...


class AliasItemLike(Protocol):
    aliases: list[str]


class AliasProvider(Protocol):
    async def fetch_alias_by_song_id(self, song_id: int) -> AliasItemLike | None: ...


@dataclass(slots=True)
class SongService:
    storage: StorageRepository
    divingfish: SongProvider
    yuzuchan: AliasProvider

    def get_song_by_game_id(self, game_id: int) -> Song | None:
        return self.storage.get_song_by_game_id(game_id)

    def get_song(self, song_id: int) -> Song | None:
        return self.storage.get_song(song_id)

    def get_songs(self, song_filter: SongFilter) -> tuple[list[Song], int]:
        return self.storage.get_songs(song_filter)

    def create_song(self, song: Song) -> Song:
        return self.storage.create_song(song)

    async def sync_from_divingfish(self) -> int:
        songs = await self.divingfish.fetch_songs()
        for song in songs:
            self.storage.upsert_song(song)
        return len(songs)

    async def refresh_aliases(self) -> int:
        songs = self.storage.get_all_songs()
        updated_count = 0
        for song in songs:
            if song.game_id is None:
                continue
            alias_item = await self.yuzuchan.fetch_alias_by_song_id(song.game_id)
            if alias_item is None or not alias_item.aliases:
                continue
            self.storage.save_song_aliases(song.id, alias_item.aliases)
            updated_count += 1
        return updated_count


@dataclass(slots=True)
class CollectorService:
    scheduler: AppScheduler
    storage: StorageRepository
    song_service: SongService
    mapper: CommentMapper | None = None
    relevance: RelevanceAnalyzer | None = None

    def trigger_collection(self, keyword: str, song_id: int | None = None) -> bool:
        return self.scheduler.add_task(CollectionTask(keyword=keyword, song_id=song_id))

    def backfill_collection(self) -> int:
        queued = 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        for song in self.song_service.storage.get_all_songs():
            if song.last_scraped:
                try:
                    last_scraped = datetime.fromisoformat(song.last_scraped)
                    if last_scraped >= cutoff:
                        continue
                except ValueError:
                    pass
            keyword = f"{song.title} 舞萌 maimai 手元 谱面确认"
            if self.trigger_collection(keyword, song.id):
                queued += 1
        return queued

    def get_song_by_game_id(self, game_id: int) -> Song | None:
        return self.song_service.get_song_by_game_id(game_id)

    def wait_until_idle(self, timeout: float = 5.0) -> bool:
        return self.scheduler.wait_until_idle(timeout=timeout)

    async def check_alias_suitability(self, song: Song, alias: str) -> bool:
        if self.relevance is None:
            return True
        return await self.relevance.check_alias_suitability(
            song.title, song.artist, alias
        )

    def update_alias_suitability(self, alias_id: int, is_suitable: bool) -> None:
        self.storage.update_song_alias_suitability(alias_id, is_suitable)

    async def map_comments_to_songs(self) -> int:
        if self.mapper is None:
            return 0
        return await self.mapper.map_comments_to_songs()

    def trigger_discovery(self, tags: list[str]) -> int:
        queued = 0
        for tag in tags:
            if self.scheduler.add_task(
                CollectionTask(keyword=tag, source="bilibili_discovery")
            ):
                queued += 1
        return queued

    async def run_maintenance_cycle(self, discovery_tags: list[str]) -> dict[str, int]:
        queued = self.trigger_discovery(discovery_tags)
        self.wait_until_idle(timeout=5.0)
        mapped = await self.map_comments_to_songs()
        return {"queued": queued, "mapped": mapped}


@dataclass(slots=True)
class AnalysisService:
    storage: StorageRepository
    pipeline: AnalysisPipeline | None = None

    @classmethod
    def with_pipeline(
        cls, storage: StorageRepository, llm: LLMClient, prompts: PromptConfig
    ) -> "AnalysisService":
        return cls(storage=storage, pipeline=AnalysisPipeline(storage, llm, prompts))

    async def analyze_song_by_game_id(self, game_id: int) -> bool:
        if self.pipeline is None:
            raise NotImplementedError("Analysis pipeline 尚未配置")
        song = self.storage.get_song_by_game_id(game_id)
        if song is None:
            raise ValueError(f"歌曲不存在: {game_id}")
        return await self.pipeline.analyze_song(song.id)

    async def analyze_batch_by_game_ids(self, game_ids: list[int]) -> tuple[int, int]:
        succeeded = 0
        failed = 0
        for game_id in game_ids:
            try:
                generated = await self.analyze_song_by_game_id(game_id)
                if generated:
                    succeeded += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        return succeeded, failed

    async def analyze_pending_songs(self, limit: int = 20) -> int:
        processed = 0
        for song in self.storage.get_all_songs():
            if processed >= limit:
                break
            if self.storage.get_analysis_result_by_song_id(song.id) is not None:
                continue
            comments = self.storage.get_comments_by_song_id(song.id)
            if not comments:
                continue
            generated = await self.analyze_song_by_game_id(song.game_id or song.id)
            if generated:
                processed += 1
        return processed

    def get_aggregated_analysis_result_by_game_id(
        self, game_id: int
    ) -> tuple[AnalysisResult | None, list[AnalysisResult]] | None:
        song = self.storage.get_song_by_game_id(game_id)
        if song is None:
            return None

        song_result = self.storage.get_analysis_result_by_song_id(song.id)
        chart_results: list[AnalysisResult] = []
        for chart in song.charts:
            result = self.storage.get_analysis_results_by_target("chart", chart.id)
            if result is not None:
                chart_results.append(result)
        return song_result, chart_results
