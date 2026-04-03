from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
import threading
from typing import Callable


@dataclass(slots=True)
class StageJob:
    reason: str


class StageRunner:
    def __init__(self, run_stage: Callable[[StageJob], None]) -> None:
        self._run_stage = run_stage
        self._queue: Queue[StageJob | None] = Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def submit(self, job: StageJob) -> None:
        self._queue.put(job)

    def clear_pending(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except Empty:
                return
            if item is None:
                self._queue.put(None)
                return

    def close(self) -> None:
        self._queue.put(None)
        self._thread.join()

    def _worker(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                return
            self._run_stage(job)
