from __future__ import annotations

from datetime import datetime, timezone

from maiecho_py.internal.scheduler.scheduler import AppScheduler
from maiecho_py.internal.status.status import StatusService


def test_status_service_exposes_scheduler_observability() -> None:
    scheduler = AppScheduler()
    scheduler.add_periodic_job(
        name="mapper",
        interval_seconds=60.0,
        callback=lambda: None,
        run_immediately=False,
    )
    scheduler._record_task(
        kind="periodic",
        name="mapper",
        status="success",
        detail="completed",
        started_at=datetime.now(timezone.utc),
    )

    status = StatusService(
        active_task_provider=scheduler.active_task_count,
        queue_size_provider=scheduler.queue_size,
        periodic_jobs_provider=scheduler.periodic_job_names,
        recent_tasks_provider=scheduler.recent_task_records,
        collector_health_provider=scheduler.collector_health,
    ).get_system_status()

    assert status.active_tasks == 0
    assert status.queued_tasks == 0
    assert status.periodic_jobs == ["mapper"]
    assert status.collector_health == []
    assert len(status.recent_tasks) == 1
    assert status.recent_tasks[0].name == "mapper"
