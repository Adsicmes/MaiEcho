from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from maiecho_py.internal.agent.mapper import CommentMapper
from maiecho_py.internal.agent.relevance import RelevanceAnalyzer
from maiecho_py.internal.collector.base import Collector
from maiecho_py.internal.collector.bilibili import BilibiliCollector
from maiecho_py.internal.collector.discovery import BilibiliDiscoveryCollector
from maiecho_py.internal.config.loader import load_app_config, load_prompt_config
from maiecho_py.internal.llm.client import LLMClient
from maiecho_py.internal.logger.logger import configure_logging
from maiecho_py.internal.provider.registry import ProviderRegistry
from maiecho_py.internal.scheduler.scheduler import AppScheduler
from maiecho_py.internal.service.services import (
    AnalysisService,
    CollectorService,
    SongService,
)
from maiecho_py.internal.storage.database import Database, build_database
from maiecho_py.internal.storage import StorageRepository
from maiecho_py.internal.status.status import StatusService


@dataclass(slots=True)
class AppContainer:
    config: object
    prompts: object
    database: Database
    providers: ProviderRegistry
    llm: LLMClient
    scheduler: AppScheduler
    status_service: StatusService
    storage: StorageRepository
    song_service: SongService
    analysis_service: AnalysisService
    collector_service: CollectorService


def build_app_container() -> AppContainer:
    config = load_app_config()
    prompts = load_prompt_config()
    configure_logging(config.log)
    database = build_database(config.database_url)
    storage = StorageRepository(database)
    providers = ProviderRegistry.from_config(config)
    llm = LLMClient.from_config(config.llm)
    collectors = cast(
        list[Collector],
        [
            BilibiliDiscoveryCollector(storage),
            BilibiliCollector(
                storage,
                cookie=config.bilibili.cookie,
                proxy=config.bilibili.proxy or None,
            ),
        ],
    )
    scheduler = AppScheduler(collectors=collectors, storage=storage)
    status_service = StatusService(
        active_task_provider=scheduler.active_task_count,
        queue_size_provider=scheduler.queue_size,
        periodic_jobs_provider=scheduler.periodic_job_names,
        recent_tasks_provider=scheduler.recent_task_records,
        collector_health_provider=scheduler.collector_health,
    )
    song_service = SongService(
        storage=storage,
        divingfish=providers.divingfish,
        yuzuchan=providers.yuzuchan,
    )
    analysis_service = AnalysisService.with_pipeline(storage, llm, prompts)
    collector_service = CollectorService(
        scheduler=scheduler,
        storage=storage,
        song_service=song_service,
        mapper=CommentMapper(storage, llm, prompts),
        relevance=RelevanceAnalyzer(llm, prompts),
    )
    scheduler.add_periodic_job(
        name="discovery",
        interval_seconds=1800.0,
        callback=lambda: collector_service.trigger_discovery(
            ["舞萌 maimai", "舞萌DX maimai", "maimai 手元"]
        ),
        run_immediately=False,
    )
    scheduler.add_periodic_job(
        name="mapper",
        interval_seconds=600.0,
        callback=collector_service.map_comments_to_songs,
        run_immediately=False,
    )
    scheduler.add_periodic_job(
        name="analysis",
        interval_seconds=900.0,
        callback=analysis_service.analyze_pending_songs,
        run_immediately=False,
    )
    return AppContainer(
        config=config,
        prompts=prompts,
        database=database,
        providers=providers,
        llm=llm,
        scheduler=scheduler,
        status_service=status_service,
        storage=storage,
        song_service=song_service,
        analysis_service=analysis_service,
        collector_service=collector_service,
    )
