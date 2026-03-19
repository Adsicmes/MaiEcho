from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import active_count
from typing import Callable

import psutil

from maiecho_py.internal.logger.logger import get_last_log_entry
from maiecho_py.internal.status.schemas import (
    CollectorHealthResponse,
    SystemStatusResponse,
    TaskRecordResponse,
)


@dataclass(slots=True)
class StatusService:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    active_task_provider: Callable[[], int] | None = None
    queue_size_provider: Callable[[], int] | None = None
    periodic_jobs_provider: Callable[[], list[str]] | None = None
    recent_tasks_provider: Callable[[], list[dict[str, str]]] | None = None
    collector_health_provider: Callable[[], list[dict[str, str]]] | None = None

    def get_system_status(self) -> SystemStatusResponse:
        process = psutil.Process()
        uptime = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        memory_mb = process.memory_info().rss / 1024 / 1024
        recent_tasks = [
            TaskRecordResponse.model_validate(item)
            for item in (
                self.recent_tasks_provider() if self.recent_tasks_provider else []
            )
        ]
        collector_health = [
            CollectorHealthResponse.model_validate(item)
            for item in (
                self.collector_health_provider()
                if self.collector_health_provider
                else []
            )
        ]
        return SystemStatusResponse(
            uptime_seconds=uptime,
            threads=active_count(),
            memory_usage_mb=round(memory_mb, 2),
            active_tasks=self.active_task_provider()
            if self.active_task_provider
            else 0,
            queued_tasks=self.queue_size_provider() if self.queue_size_provider else 0,
            periodic_jobs=self.periodic_jobs_provider()
            if self.periodic_jobs_provider
            else [],
            collector_health=collector_health,
            recent_tasks=recent_tasks,
            last_log_entry=get_last_log_entry(),
        )
