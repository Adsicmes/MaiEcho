from __future__ import annotations

from pydantic import BaseModel


class TaskRecordResponse(BaseModel):
    kind: str
    name: str
    status: str
    detail: str
    started_at: str
    finished_at: str


class CollectorHealthResponse(BaseModel):
    source: str
    status: str
    last_error: str
    ban_until: str


class SystemStatusResponse(BaseModel):
    uptime_seconds: float
    threads: int
    memory_usage_mb: float
    active_tasks: int
    queued_tasks: int
    periodic_jobs: list[str]
    collector_health: list[CollectorHealthResponse]
    recent_tasks: list[TaskRecordResponse]
    last_log_entry: str
