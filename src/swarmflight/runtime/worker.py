from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from swarmflight.runtime.models import Task, TaskResult

TaskHandler = Callable[[Task], dict[str, Any]]


class Worker(Protocol):
    worker_id: str

    def run(self, task: Task) -> TaskResult:
        """Execute a task and return a structured result."""


class FunctionWorker:
    """Worker adapter that wraps a Python callable."""

    def __init__(self, worker_id: str, handler: TaskHandler) -> None:
        self.worker_id = worker_id
        self._handler = handler

    def run(self, task: Task) -> TaskResult:
        try:
            output = self._handler(task)
            return TaskResult(
                task_id=task.task_id,
                worker_id=self.worker_id,
                ok=True,
                output=output,
            )
        except Exception as exc:  # noqa: BLE001 - this boundary captures worker failures
            return TaskResult(
                task_id=task.task_id,
                worker_id=self.worker_id,
                ok=False,
                output={},
                error=str(exc),
            )
