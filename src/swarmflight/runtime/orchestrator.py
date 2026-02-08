from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from swarmflight.runtime.mailbox import Mailbox
from swarmflight.runtime.models import Message, Task, TaskResult, TaskStatus
from swarmflight.runtime.worker import Worker


@dataclass(slots=True)
class SchedulerState:
    cursor: int = 0


class Orchestrator:
    """Simple in-memory orchestrator with round-robin worker selection."""

    def __init__(self, mailbox: Mailbox | None = None) -> None:
        self.mailbox = mailbox or Mailbox()
        self._workers: dict[str, Worker] = {}
        self._tasks: dict[str, Task] = {}
        self._ready_queue: deque[str] = deque()
        self._blocked: set[str] = set()
        self._dependents: dict[str, set[str]] = defaultdict(set)
        self._results: dict[str, TaskResult] = {}
        self._attempt_history: dict[str, list[TaskResult]] = defaultdict(list)
        self._result_order: list[str] = []
        self._scheduler = SchedulerState()

    def register_worker(self, worker: Worker) -> None:
        if worker.worker_id in self._workers:
            raise ValueError(f"worker already registered: {worker.worker_id}")
        self._workers[worker.worker_id] = worker

    def submit_task(
        self,
        description: str,
        payload: dict[str, Any] | None = None,
        worker_id: str | None = None,
        dependencies: list[str] | tuple[str, ...] | None = None,
        max_retries: int = 0,
        task_id: str | None = None,
    ) -> Task:
        if worker_id is not None and worker_id not in self._workers:
            raise KeyError(f"unknown worker: {worker_id}")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        dependency_ids = tuple(dict.fromkeys(dependencies or ()))
        for dependency_id in dependency_ids:
            if dependency_id not in self._tasks:
                raise KeyError(f"unknown dependency: {dependency_id}")

        new_task_id = task_id or uuid4().hex
        if new_task_id in self._tasks:
            raise ValueError(f"task already exists: {new_task_id}")

        task = Task(
            task_id=new_task_id,
            description=description,
            payload=payload or {},
            dependencies=dependency_ids,
            max_retries=max_retries,
            worker_id=worker_id,
        )
        self._tasks[task.task_id] = task

        for dependency_id in dependency_ids:
            self._dependents[dependency_id].add(task.task_id)

        if self._dependency_failed(task):
            failed_dependency = self._first_failed_dependency(task)
            self._skip_task(task, reason=f"dependency failed: {failed_dependency}")
        elif self._dependencies_completed(task):
            self._ready_queue.append(task.task_id)
        else:
            self._blocked.add(task.task_id)

        self.mailbox.send(
            Message(
                sender="orchestrator",
                recipient="orchestrator",
                kind="task_submitted",
                content={
                    "task_id": task.task_id,
                    "dependency_count": len(task.dependencies),
                },
            )
        )
        return task

    def run_next(self) -> TaskResult | None:
        self._refresh_blocked_tasks()
        if not self._ready_queue:
            return None
        task_id = self._ready_queue.popleft()
        return self.run_task(task_id)

    def run_all(self) -> list[TaskResult]:
        start_index = len(self._result_order)

        while self.run_next() is not None:
            pass

        self._refresh_blocked_tasks()
        return [self._results[task_id] for task_id in self._result_order[start_index:]]

    def run_task(self, task_id: str) -> TaskResult:
        task = self._tasks[task_id]

        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED):
            return self._results[task_id]

        if task_id in self._blocked:
            if self._dependency_failed(task):
                failed_dependency = self._first_failed_dependency(task)
                self._skip_task(task, reason=f"dependency failed: {failed_dependency}")
                return self._results[task_id]
            raise RuntimeError(f"task is blocked by dependencies: {task_id}")

        if not self._dependencies_completed(task):
            raise RuntimeError(f"task dependencies are not complete: {task_id}")

        worker = self._select_worker(task)
        task.status = TaskStatus.RUNNING
        task.attempts += 1
        result = worker.run(task)
        result.attempt = task.attempts
        self._attempt_history[task_id].append(result)

        if result.ok:
            task.status = TaskStatus.COMPLETED
            self._store_terminal_result(result)
            self.mailbox.send(
                Message(
                    sender=result.worker_id,
                    recipient="orchestrator",
                    kind="task_finished",
                    content={"task_id": task_id, "ok": True},
                )
            )
            self._resolve_dependents(task_id)
            return result

        if task.attempts <= task.max_retries:
            task.status = TaskStatus.PENDING
            self._ready_queue.append(task_id)
            self.mailbox.send(
                Message(
                    sender=result.worker_id,
                    recipient="orchestrator",
                    kind="task_retrying",
                    content={
                        "task_id": task_id,
                        "attempt": task.attempts,
                        "max_retries": task.max_retries,
                    },
                )
            )
            return result

        task.status = TaskStatus.FAILED
        self._store_terminal_result(result)
        self.mailbox.send(
            Message(
                sender=result.worker_id,
                recipient="orchestrator",
                kind="task_finished",
                content={"task_id": task_id, "ok": False},
            )
        )
        self._resolve_dependents(task_id)
        return result

    def get_task(self, task_id: str) -> Task:
        return self._tasks[task_id]

    def result_for(self, task_id: str) -> TaskResult | None:
        return self._results.get(task_id)

    def attempts_for(self, task_id: str) -> list[TaskResult]:
        return list(self._attempt_history.get(task_id, ()))

    def list_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def list_results(self) -> list[TaskResult]:
        return [self._results[task_id] for task_id in self._result_order]

    def _select_worker(self, task: Task) -> Worker:
        if task.worker_id is not None:
            return self._workers[task.worker_id]

        if not self._workers:
            raise RuntimeError("no workers registered")

        worker_ids = list(self._workers)
        worker_id = worker_ids[self._scheduler.cursor % len(worker_ids)]
        self._scheduler.cursor += 1
        task.worker_id = worker_id
        return self._workers[worker_id]

    def _store_terminal_result(self, result: TaskResult) -> None:
        if result.task_id not in self._results:
            self._result_order.append(result.task_id)
        self._results[result.task_id] = result

    def _resolve_dependents(self, task_id: str) -> None:
        for dependent_id in self._dependents.get(task_id, ()):
            dependent_task = self._tasks[dependent_id]
            if dependent_task.status is not TaskStatus.PENDING:
                continue

            if self._dependency_failed(dependent_task):
                failed_dependency = self._first_failed_dependency(dependent_task)
                self._skip_task(
                    dependent_task,
                    reason=f"dependency failed: {failed_dependency}",
                )
                continue

            if self._dependencies_completed(dependent_task):
                self._blocked.discard(dependent_id)
                if dependent_id not in self._ready_queue:
                    self._ready_queue.append(dependent_id)

    def _refresh_blocked_tasks(self) -> None:
        for task_id in list(self._blocked):
            task = self._tasks[task_id]
            if task.status is not TaskStatus.PENDING:
                self._blocked.discard(task_id)
                continue

            if self._dependency_failed(task):
                failed_dependency = self._first_failed_dependency(task)
                self._skip_task(task, reason=f"dependency failed: {failed_dependency}")
                continue

            if self._dependencies_completed(task):
                self._blocked.discard(task_id)
                self._ready_queue.append(task_id)

    def _skip_task(self, task: Task, reason: str) -> None:
        task.status = TaskStatus.SKIPPED
        self._blocked.discard(task.task_id)
        result = TaskResult(
            task_id=task.task_id,
            worker_id="orchestrator",
            ok=False,
            attempt=task.attempts,
            output={},
            error=reason,
        )
        self._store_terminal_result(result)
        self.mailbox.send(
            Message(
                sender="orchestrator",
                recipient="orchestrator",
                kind="task_skipped",
                content={"task_id": task.task_id, "reason": reason},
            )
        )
        self._resolve_dependents(task.task_id)

    def _dependencies_completed(self, task: Task) -> bool:
        for dependency_id in task.dependencies:
            dependency = self._tasks[dependency_id]
            if dependency.status is not TaskStatus.COMPLETED:
                return False
        return True

    def _dependency_failed(self, task: Task) -> bool:
        for dependency_id in task.dependencies:
            dependency = self._tasks[dependency_id]
            if dependency.status in (TaskStatus.FAILED, TaskStatus.SKIPPED):
                return True
        return False

    def _first_failed_dependency(self, task: Task) -> str:
        for dependency_id in task.dependencies:
            dependency = self._tasks[dependency_id]
            if dependency.status in (TaskStatus.FAILED, TaskStatus.SKIPPED):
                return dependency_id
        raise RuntimeError("no failed dependency")
