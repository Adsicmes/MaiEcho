from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Event, Lock, Thread
from time import monotonic, sleep
from typing import Awaitable, Callable

from maiecho_py.internal.collector.base import CollectionTask, Collector
from maiecho_py.internal.storage import StorageRepository


PeriodicCallback = Callable[[], object | Awaitable[object]]


@dataclass(slots=True)
class PeriodicJob:
    name: str
    interval_seconds: float
    callback: PeriodicCallback
    run_immediately: bool = True


@dataclass(slots=True)
class TaskExecutionRecord:
    kind: str
    name: str
    status: str
    detail: str
    started_at: str
    finished_at: str


@dataclass(slots=True)
class CollectorHealthRecord:
    source: str
    status: str
    last_error: str
    ban_until: str


class AppScheduler:
    def __init__(
        self,
        collectors: Sequence[Collector] | None = None,
        storage: StorageRepository | None = None,
        worker_count: int = 1,
        buffer_size: int = 1000,
    ) -> None:
        self._collectors = list(collectors or [])
        self._storage = storage
        self._worker_count = worker_count
        self._queue: Queue[CollectionTask] = Queue(maxsize=buffer_size)
        self._stop_event = Event()
        self._workers: list[Thread] = []
        self._periodic_jobs: list[PeriodicJob] = []
        self._job_threads: list[Thread] = []
        self._active_background_tasks = 0
        self._task_lock = Lock()
        self._recent_task_records: list[TaskExecutionRecord] = []

    def add_periodic_job(
        self,
        name: str,
        interval_seconds: float,
        callback: PeriodicCallback,
        *,
        run_immediately: bool = True,
    ) -> None:
        self._periodic_jobs.append(
            PeriodicJob(
                name=name,
                interval_seconds=interval_seconds,
                callback=callback,
                run_immediately=run_immediately,
            )
        )

    def start(self) -> None:
        if self._workers or self._job_threads:
            return
        self._stop_event.clear()
        for index in range(self._worker_count):
            worker = Thread(
                target=self._worker, name=f"collector-worker-{index}", daemon=True
            )
            worker.start()
            self._workers.append(worker)
        for job in self._periodic_jobs:
            thread = Thread(
                target=self._job_worker,
                args=(job,),
                name=f"periodic-job-{job.name}",
                daemon=True,
            )
            thread.start()
            self._job_threads.append(thread)

    def shutdown(self, wait: bool = False) -> None:
        self._stop_event.set()
        if wait:
            self.wait_until_idle(timeout=5.0)
        for worker in self._workers:
            worker.join(timeout=1.0)
        self._workers.clear()
        for thread in self._job_threads:
            thread.join(timeout=1.0)
        self._job_threads.clear()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except Empty:
                break

    def add_task(self, task: CollectionTask) -> bool:
        if self._stop_event.is_set():
            return False
        try:
            self._queue.put_nowait(task)
            return True
        except Exception:
            return False

    def wait_until_idle(self, timeout: float = 5.0) -> bool:
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            sleep(0.05)
        return self._queue.unfinished_tasks == 0

    def queue_size(self) -> int:
        return self._queue.qsize()

    def active_task_count(self) -> int:
        with self._task_lock:
            return self._queue.unfinished_tasks + self._active_background_tasks

    def periodic_job_names(self) -> list[str]:
        return [job.name for job in self._periodic_jobs]

    def recent_task_records(self) -> list[dict[str, str]]:
        with self._task_lock:
            return [asdict(record) for record in self._recent_task_records]

    def collector_health(self) -> list[dict[str, str]]:
        health: list[dict[str, str]] = []
        for collector in self._collectors:
            if hasattr(collector, "health_snapshot"):
                snapshot = getattr(collector, "health_snapshot")()
                health.append(
                    {
                        "source": str(snapshot.get("source", collector.source_name)),
                        "status": str(snapshot.get("status", "healthy")),
                        "last_error": str(snapshot.get("last_error", "")),
                        "ban_until": str(snapshot.get("ban_until", "")),
                    }
                )
            else:
                health.append(
                    {
                        "source": collector.source_name,
                        "status": "healthy",
                        "last_error": "",
                        "ban_until": "",
                    }
                )
        return health

    async def close_collectors(self) -> None:
        for collector in self._collectors:
            with suppress(RuntimeError):
                await collector.close()

    def _job_worker(self, job: PeriodicJob) -> None:
        if job.run_immediately:
            self._execute_periodic_job(job)
        while not self._stop_event.wait(job.interval_seconds):
            self._execute_periodic_job(job)

    def _execute_periodic_job(self, job: PeriodicJob) -> None:
        if self._stop_event.is_set():
            return
        started_at = datetime.now(timezone.utc)
        self._mark_background_task(1)
        try:
            result = job.callback()
            if asyncio.iscoroutine(result):
                asyncio.run(result)
            self._record_task(
                kind="periodic",
                name=job.name,
                status="success",
                detail="completed",
                started_at=started_at,
            )
        except Exception as exc:
            self._record_task(
                kind="periodic",
                name=job.name,
                status="failed",
                detail=self._exception_detail(exc),
                started_at=started_at,
            )
            pass
        finally:
            self._mark_background_task(-1)

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                task = self._queue.get(timeout=0.1)
            except Empty:
                continue
            started_at = datetime.now(timezone.utc)
            try:
                asyncio.run(self._process_task(task))
                self._record_task(
                    kind="collector",
                    name=task.keyword,
                    status="success",
                    detail=task.source or "all",
                    started_at=started_at,
                )
            except Exception as exc:
                self._record_task(
                    kind="collector",
                    name=task.keyword,
                    status="failed",
                    detail=f"{task.source or 'all'}: {self._exception_detail(exc)}",
                    started_at=started_at,
                )
                pass
            finally:
                self._queue.task_done()

    async def _process_task(self, task: CollectionTask) -> None:
        for collector in self._collectors:
            if task.source and collector.source_name != task.source:
                continue
            await collector.collect(task.keyword, task.song_id)
            if task.song_id is not None and self._storage is not None:
                self._storage.update_song_last_scraped_time(task.song_id)

    def _mark_background_task(self, delta: int) -> None:
        with self._task_lock:
            self._active_background_tasks += delta

    def _record_task(
        self,
        *,
        kind: str,
        name: str,
        status: str,
        detail: str,
        started_at: datetime,
    ) -> None:
        finished_at = datetime.now(timezone.utc)
        record = TaskExecutionRecord(
            kind=kind,
            name=name,
            status=status,
            detail=detail,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
        )
        with self._task_lock:
            self._recent_task_records.append(record)
            self._recent_task_records = self._recent_task_records[-10:]

    @staticmethod
    def _exception_detail(exc: Exception) -> str:
        message = str(exc).strip()
        if not message:
            return exc.__class__.__name__
        return f"{exc.__class__.__name__}: {message}"
