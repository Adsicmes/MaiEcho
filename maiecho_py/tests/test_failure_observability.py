from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

import maiecho_py.internal.storage as storage
from maiecho_py.internal.collector.base import CollectionTask
from maiecho_py.internal.collector.bilibili import BilibiliCollector
from maiecho_py.internal.scheduler.scheduler import AppScheduler
from maiecho_py.internal.status.status import StatusService
from maiecho_py.internal.storage.database import build_database


def test_status_exposes_bilibili_ban_and_last_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/x/web-interface/search/all/v2"):
            return httpx.Response(403, json={})
        raise AssertionError(f"unexpected path: {request.url.path}")

    database = build_database(str(tmp_path / "failure.db"))
    repository = storage.StorageRepository(database)
    collector = BilibiliCollector(
        repository,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    scheduler = AppScheduler(collectors=[collector], storage=repository)
    scheduler.add_task(CollectionTask(keyword="blocked"))
    scheduler.start()
    scheduler.wait_until_idle(timeout=2.0)
    scheduler.shutdown(wait=True)

    status = StatusService(
        active_task_provider=scheduler.active_task_count,
        queue_size_provider=scheduler.queue_size,
        periodic_jobs_provider=scheduler.periodic_job_names,
        recent_tasks_provider=scheduler.recent_task_records,
        collector_health_provider=scheduler.collector_health,
    ).get_system_status()

    assert status.collector_health[0].source == "bilibili"
    assert status.collector_health[0].status == "banned"
    assert "rate-limited" in status.collector_health[0].last_error
    assert status.collector_health[0].ban_until != ""
    assert status.recent_tasks[-1].status == "failed"
    assert "HTTPStatusError" in status.recent_tasks[-1].detail
    assert "all:" in status.recent_tasks[-1].detail

    asyncio.run(collector.close())
    database.dispose()
