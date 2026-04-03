from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Callable


@dataclass(slots=True)
class ConsolidationJob:
    memory_root: Path


class ConsolidationRunner:
    def __init__(
        self,
        *,
        run_consolidation: Callable[[ConsolidationJob], None],
    ) -> None:
        self._run_consolidation = run_consolidation
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="memory-consolidate")
        self._current_future: Future[None] | None = None
        self._pending_job: ConsolidationJob | None = None
        self._accepting_submissions = True

    def submit(self, job: ConsolidationJob) -> None:
        with self._lock:
            if not self._accepting_submissions:
                return
            if self._current_future is None or self._current_future.done():
                self._schedule_locked(job)
                return
            self._pending_job = job

    def drain(self) -> None:
        while True:
            with self._lock:
                current = self._current_future
                pending = self._pending_job
            if current is not None:
                current.result()
                continue
            if pending is not None:
                with self._lock:
                    if self._current_future is None and self._pending_job is not None:
                        self._schedule_locked(self._pending_job)
                        self._pending_job = None
                continue
            break

    def close(self) -> None:
        with self._lock:
            self._accepting_submissions = False
        self.drain()
        self._executor.shutdown(wait=True)

    def _schedule_locked(self, job: ConsolidationJob) -> None:
        self._current_future = self._executor.submit(self._run_job, job)

    def _run_job(self, job: ConsolidationJob) -> None:
        try:
            self._run_consolidation(job)
        except Exception:
            pass
        finally:
            with self._lock:
                self._current_future = None
                if self._pending_job is not None:
                    next_job = self._pending_job
                    self._pending_job = None
                    self._schedule_locked(next_job)
