from __future__ import annotations

from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from swarmflight.runtime.actions import Observation
from swarmflight.runtime.checkpoint import (
    RunCheckpoint,
    RunCheckpointStore,
    deserialize_result,
    deserialize_task,
    serialize_result,
    serialize_task,
)
from swarmflight.runtime.concurrency import ConcurrencyLimits, ConcurrencyManager, ConcurrencyToken
from swarmflight.runtime.mailbox import Mailbox
from swarmflight.runtime.models import Message, Task, TaskResult, TaskStatus
from swarmflight.runtime.policy import HeuristicPolicy, Policy
from swarmflight.runtime.trace import TraceRecorder
from swarmflight.runtime.worker import Worker


@dataclass(slots=True)
class SchedulerState:
    cursor: int = 0


class Orchestrator:
    """Simple in-memory orchestrator with round-robin worker selection."""

    def __init__(
        self,
        mailbox: Mailbox | None = None,
        policy: Policy | None = None,
        trace_recorder: TraceRecorder | None = None,
        concurrency_limits: ConcurrencyLimits | None = None,
        run_id: str | None = None,
    ) -> None:
        self.mailbox = mailbox or Mailbox()
        self.policy = policy or HeuristicPolicy()
        self.trace = trace_recorder
        if self.trace is not None and run_id is None:
            self.run_id = self.trace.run_id
        else:
            self.run_id = run_id or uuid4().hex
            if self.trace is not None:
                self.trace.run_id = self.run_id
        self.concurrency = ConcurrencyManager(concurrency_limits)
        self._workers: dict[str, Worker] = {}
        self._tasks: dict[str, Task] = {}
        self._ready_queue: deque[str] = deque()
        self._running: set[str] = set()
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
        self._record("worker_registered", worker_id=worker.worker_id)

    def submit_task(
        self,
        description: str,
        payload: dict[str, Any] | None = None,
        worker_id: str | None = None,
        dependencies: list[str] | tuple[str, ...] | None = None,
        profile: str = "default",
        provider: str | None = None,
        stale_timeout_ms: int | None = None,
        max_runtime_ms: int | None = None,
        max_retries: int = 0,
        task_id: str | None = None,
    ) -> Task:
        if worker_id is not None and worker_id not in self._workers:
            raise KeyError(f"unknown worker: {worker_id}")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if not profile:
            raise ValueError("profile must be non-empty")
        if stale_timeout_ms is not None and stale_timeout_ms <= 0:
            raise ValueError("stale_timeout_ms must be > 0")
        if max_runtime_ms is not None and max_runtime_ms <= 0:
            raise ValueError("max_runtime_ms must be > 0")

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
            profile=profile,
            provider=provider,
            stale_timeout_ms=stale_timeout_ms,
            max_runtime_ms=max_runtime_ms,
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
            task.queued_at = datetime.now(UTC)
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
        self._record(
            "task_submitted",
            task_id=task.task_id,
            dependency_count=len(task.dependencies),
            max_retries=task.max_retries,
        )
        return task

    def run_next(self) -> TaskResult | None:
        self._refresh_blocked_tasks()
        action = self.policy.choose(self.observation())
        self._record("policy_action", action=action.action_type.value, payload=action.payload)
        if not self._ready_queue:
            return None
        task_id = self._ready_queue.popleft()
        return self.run_task(task_id)

    def run_tick(self) -> list[TaskResult]:
        self._refresh_blocked_tasks()
        action = self.policy.choose(self.observation())
        self._record("policy_action", action=action.action_type.value, payload=action.payload)

        if not self._ready_queue:
            return []
        if not self._workers:
            raise RuntimeError("no workers registered")

        ready_count = len(self._ready_queue)
        deferred: deque[str] = deque()
        scheduled: list[tuple[Task, Worker, ConcurrencyToken]] = []
        reserved_worker_ids: set[str] = set()

        for _ in range(ready_count):
            task_id = self._ready_queue.popleft()
            task = self._tasks[task_id]
            if task.status is not TaskStatus.PENDING:
                continue

            if self._is_task_stale(task):
                self._mark_task_stale(task, reason="stale timeout exceeded before execution")
                continue

            worker = self._select_worker(task, reserved_worker_ids)
            if worker is None:
                deferred.append(task_id)
                continue

            token = self.concurrency.try_acquire(profile=task.profile, provider=task.provider)
            if token is None:
                deferred.append(task_id)
                continue

            reserved_worker_ids.add(worker.worker_id)
            self._begin_attempt(task)
            self._record(
                "task_scheduled",
                task_id=task_id,
                worker_id=worker.worker_id,
                profile=task.profile,
            )
            scheduled.append((task, worker, token))

        self._ready_queue.extend(deferred)
        if not scheduled:
            return []

        attempt_results: list[TaskResult] = []

        with ThreadPoolExecutor(max_workers=len(scheduled)) as executor:
            future_map = {
                executor.submit(self._run_worker_attempt, task, worker): (task, token)
                for task, worker, token in scheduled
            }

            for future in as_completed(future_map):
                task, token = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001 - safeguard boundary for worker failures
                    result = TaskResult(
                        task_id=task.task_id,
                        worker_id=task.worker_id or "unknown-worker",
                        ok=False,
                        attempt=task.attempts,
                        output={},
                        error=str(exc),
                    )
                attempt_results.append(
                    self._finalize_attempt(task=task, result=result, token=token)
                )

        self._refresh_blocked_tasks()
        return attempt_results

    def run_until_idle(
        self,
        *,
        checkpoint_path: str | Path | None = None,
        checkpoint_metadata: dict[str, Any] | None = None,
        checkpoint_interval_ticks: int = 1,
        max_ticks: int | None = None,
        checkpoint_store: RunCheckpointStore | None = None,
    ) -> list[TaskResult]:
        if checkpoint_interval_ticks < 1:
            raise ValueError("checkpoint_interval_ticks must be >= 1")
        if max_ticks is not None and max_ticks < 1:
            raise ValueError("max_ticks must be >= 1")

        start_index = len(self._result_order)
        tick_count = 0

        while True:
            attempts = self.run_tick()
            if attempts:
                tick_count += 1
                if checkpoint_path is not None and tick_count % checkpoint_interval_ticks == 0:
                    self.save_checkpoint(
                        path=checkpoint_path,
                        metadata=checkpoint_metadata,
                        store=checkpoint_store,
                    )
                if max_ticks is not None and tick_count >= max_ticks:
                    if checkpoint_path is not None:
                        self.save_checkpoint(
                            path=checkpoint_path,
                            metadata=checkpoint_metadata,
                            store=checkpoint_store,
                        )
                    break
                continue
            self._refresh_blocked_tasks()
            if not self._ready_queue and not self._running:
                break

        if checkpoint_path is not None:
            self.save_checkpoint(
                path=checkpoint_path,
                metadata=checkpoint_metadata,
                store=checkpoint_store,
            )

        return [self._results[task_id] for task_id in self._result_order[start_index:]]

    def run_all(self) -> list[TaskResult]:
        return self.run_until_idle()

    def run_task(self, task_id: str) -> TaskResult:
        task = self._tasks[task_id]

        if task.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.SKIPPED,
            TaskStatus.CANCELLED,
            TaskStatus.STALE,
        ):
            return self._results[task_id]

        if task_id in self._blocked:
            if self._dependency_failed(task):
                failed_dependency = self._first_failed_dependency(task)
                self._skip_task(task, reason=f"dependency failed: {failed_dependency}")
                return self._results[task_id]
            raise RuntimeError(f"task is blocked by dependencies: {task_id}")

        if not self._dependencies_completed(task):
            raise RuntimeError(f"task dependencies are not complete: {task_id}")

        if self._is_task_stale(task):
            self._mark_task_stale(task, reason="stale timeout exceeded before execution")
            return self._results[task_id]

        worker = self._select_worker(task)
        if worker is None:
            raise RuntimeError(f"no available worker for task: {task_id}")

        token = self.concurrency.try_acquire(profile=task.profile, provider=task.provider)
        if token is None:
            raise RuntimeError(f"concurrency limit reached for task profile: {task.profile}")

        self._begin_attempt(task)
        result = self._run_worker_attempt(task, worker)
        return self._finalize_attempt(task=task, result=result, token=token)

    def observation(self) -> Observation:
        tasks = self._tasks.values()
        running = len(self._running)
        completed = sum(task.status is TaskStatus.COMPLETED for task in tasks)
        failed = sum(
            task.status in (TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.STALE)
            for task in tasks
        )
        skipped = sum(task.status is TaskStatus.SKIPPED for task in tasks)
        return Observation(
            ready_tasks=len(self._ready_queue),
            blocked_tasks=len(self._blocked),
            running_tasks=running,
            completed_tasks=completed,
            failed_tasks=failed,
            skipped_tasks=skipped,
            workers=len(self._workers),
        )

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

    def create_checkpoint(self, metadata: dict[str, Any] | None = None) -> RunCheckpoint:
        return RunCheckpoint(
            run_id=self.run_id,
            created_at=datetime.now(UTC).isoformat(),
            ready_queue=list(self._ready_queue),
            blocked=sorted(self._blocked),
            running=sorted(self._running),
            scheduler_cursor=self._scheduler.cursor,
            result_order=list(self._result_order),
            tasks={task_id: serialize_task(task) for task_id, task in self._tasks.items()},
            results={
                task_id: serialize_result(result) for task_id, result in self._results.items()
            },
            attempt_history={
                task_id: [serialize_result(result) for result in results]
                for task_id, results in self._attempt_history.items()
            },
            metadata=dict(metadata or {}),
        )

    def save_checkpoint(
        self,
        path: str | Path,
        metadata: dict[str, Any] | None = None,
        store: RunCheckpointStore | None = None,
    ) -> RunCheckpoint:
        checkpoint = self.create_checkpoint(metadata=metadata)
        checkpoint_store = store or RunCheckpointStore()
        checkpoint_store.save(path=path, checkpoint=checkpoint)
        self._record(
            "checkpoint_saved",
            path=str(path),
            ready_tasks=len(checkpoint.ready_queue),
            blocked_tasks=len(checkpoint.blocked),
            running_tasks=len(checkpoint.running),
        )
        return checkpoint

    def load_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        self.run_id = checkpoint.run_id
        if self.trace is not None:
            self.trace.run_id = self.run_id

        self._tasks = {
            task_id: deserialize_task(task_payload)
            for task_id, task_payload in checkpoint.tasks.items()
        }
        self._results = {
            task_id: deserialize_result(result_payload)
            for task_id, result_payload in checkpoint.results.items()
        }
        self._attempt_history = defaultdict(
            list,
            {
                task_id: [deserialize_result(payload) for payload in result_payloads]
                for task_id, result_payloads in checkpoint.attempt_history.items()
            },
        )
        self._ready_queue = deque(checkpoint.ready_queue)
        self._blocked = set(checkpoint.blocked)
        self._running = set(checkpoint.running)
        self._result_order = list(checkpoint.result_order)
        self._scheduler.cursor = checkpoint.scheduler_cursor

        self._dependents = defaultdict(set)
        for task in self._tasks.values():
            for dependency_id in task.dependencies:
                self._dependents[dependency_id].add(task.task_id)

        if self._workers:
            for task in self._tasks.values():
                if task.worker_id is not None and task.worker_id not in self._workers:
                    raise KeyError(f"unknown worker in checkpoint: {task.worker_id}")

        if self._running:
            for task_id in list(self._running):
                task = self._tasks.get(task_id)
                if task is None:
                    continue
                if task.status is TaskStatus.RUNNING:
                    task.status = TaskStatus.PENDING
                    task.queued_at = datetime.now(UTC)
                    if task_id not in self._ready_queue:
                        self._ready_queue.appendleft(task_id)
            self._running.clear()

        self._record(
            "checkpoint_loaded",
            ready_tasks=len(self._ready_queue),
            blocked_tasks=len(self._blocked),
            task_count=len(self._tasks),
        )

    @classmethod
    def from_checkpoint_file(
        cls,
        path: str | Path,
        *,
        mailbox: Mailbox | None = None,
        policy: Policy | None = None,
        trace_recorder: TraceRecorder | None = None,
        concurrency_limits: ConcurrencyLimits | None = None,
        store: RunCheckpointStore | None = None,
    ) -> Orchestrator:
        checkpoint_store = store or RunCheckpointStore()
        checkpoint = checkpoint_store.load(path)
        orchestrator = cls(
            mailbox=mailbox,
            policy=policy,
            trace_recorder=trace_recorder,
            concurrency_limits=concurrency_limits,
            run_id=checkpoint.run_id,
        )
        orchestrator.load_checkpoint(checkpoint)
        return orchestrator

    def _select_worker(
        self, task: Task, reserved_worker_ids: set[str] | None = None
    ) -> Worker | None:
        if not self._workers:
            raise RuntimeError("no workers registered")

        reserved = reserved_worker_ids or set()

        if task.worker_id is not None:
            if task.worker_id in reserved:
                return None
            return self._workers[task.worker_id]

        worker_ids = list(self._workers)
        if not worker_ids:
            raise RuntimeError("no workers registered")

        preferred_worker_ids = [
            worker_id
            for worker_id, worker in self._workers.items()
            if getattr(worker, "profile", "default") == task.profile
        ]
        eligible = set(preferred_worker_ids or worker_ids)

        start = self._scheduler.cursor
        for offset in range(len(worker_ids)):
            candidate_id = worker_ids[(start + offset) % len(worker_ids)]
            if candidate_id not in eligible or candidate_id in reserved:
                continue
            self._scheduler.cursor = start + offset + 1
            task.worker_id = candidate_id
            return self._workers[candidate_id]

        return None

    def _begin_attempt(self, task: Task) -> None:
        task.status = TaskStatus.RUNNING
        task.attempts += 1
        task.started_at = datetime.now(UTC)
        task.ended_at = None
        self._running.add(task.task_id)

    def _run_worker_attempt(self, task: Task, worker: Worker) -> TaskResult:
        try:
            result = worker.run(task)
        except Exception as exc:  # noqa: BLE001 - worker boundary
            result = TaskResult(
                task_id=task.task_id,
                worker_id=task.worker_id or "unknown-worker",
                ok=False,
                attempt=task.attempts,
                output={},
                error=str(exc),
            )
        result.attempt = task.attempts
        return result

    def _finalize_attempt(
        self, task: Task, result: TaskResult, token: ConcurrencyToken
    ) -> TaskResult:
        task_id = task.task_id
        self._running.discard(task_id)
        task.ended_at = datetime.now(UTC)
        self.concurrency.release(token)

        self._attempt_history[task_id].append(result)
        self._record(
            "task_attempt",
            task_id=task_id,
            worker_id=result.worker_id,
            attempt=result.attempt,
            ok=result.ok,
        )

        if self._runtime_exceeded(task):
            stale_result = TaskResult(
                task_id=task_id,
                worker_id=result.worker_id,
                ok=False,
                attempt=result.attempt,
                output={},
                error=f"max runtime exceeded: {task.max_runtime_ms}ms",
            )
            task.status = TaskStatus.STALE
            self._store_terminal_result(stale_result)
            self.mailbox.send(
                Message(
                    sender="orchestrator",
                    recipient="orchestrator",
                    kind="task_stale",
                    content={
                        "task_id": task_id,
                        "max_runtime_ms": task.max_runtime_ms,
                    },
                )
            )
            self._record("task_stale", task_id=task_id, max_runtime_ms=task.max_runtime_ms)
            self._resolve_dependents(task_id)
            return stale_result

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
            task.queued_at = datetime.now(UTC)
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
            self._record(
                "task_retrying",
                task_id=task_id,
                attempt=task.attempts,
                max_retries=task.max_retries,
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

    def _runtime_exceeded(self, task: Task) -> bool:
        if task.max_runtime_ms is None:
            return False
        if task.started_at is None or task.ended_at is None:
            return False
        elapsed_ms = (task.ended_at - task.started_at).total_seconds() * 1000
        return elapsed_ms > task.max_runtime_ms

    def _is_task_stale(self, task: Task) -> bool:
        if task.stale_timeout_ms is None:
            return False
        if task.status is not TaskStatus.PENDING:
            return False
        elapsed_ms = (datetime.now(UTC) - task.queued_at).total_seconds() * 1000
        return elapsed_ms > task.stale_timeout_ms

    def _mark_task_stale(self, task: Task, reason: str) -> None:
        task.status = TaskStatus.STALE
        self._blocked.discard(task.task_id)
        self._running.discard(task.task_id)
        task.ended_at = datetime.now(UTC)
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
                kind="task_stale",
                content={"task_id": task.task_id, "reason": reason},
            )
        )
        self._record("task_stale", task_id=task.task_id, reason=reason)
        self._resolve_dependents(task.task_id)

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
                    dependent_task.queued_at = datetime.now(UTC)
                    self._ready_queue.append(dependent_id)

    def _refresh_blocked_tasks(self) -> None:
        for task_id in list(self._blocked):
            task = self._tasks[task_id]
            if task.status is not TaskStatus.PENDING:
                self._blocked.discard(task_id)
                continue

            if self._is_task_stale(task):
                self._mark_task_stale(task, reason="stale timeout while waiting on dependencies")
                continue

            if self._dependency_failed(task):
                failed_dependency = self._first_failed_dependency(task)
                self._skip_task(task, reason=f"dependency failed: {failed_dependency}")
                continue

            if self._dependencies_completed(task):
                self._blocked.discard(task_id)
                task.queued_at = datetime.now(UTC)
                self._ready_queue.append(task_id)

    def _skip_task(self, task: Task, reason: str) -> None:
        task.status = TaskStatus.SKIPPED
        self._blocked.discard(task.task_id)
        self._running.discard(task.task_id)
        task.ended_at = datetime.now(UTC)
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
            if dependency.status in (
                TaskStatus.FAILED,
                TaskStatus.SKIPPED,
                TaskStatus.CANCELLED,
                TaskStatus.STALE,
            ):
                return True
        return False

    def _first_failed_dependency(self, task: Task) -> str:
        for dependency_id in task.dependencies:
            dependency = self._tasks[dependency_id]
            if dependency.status in (
                TaskStatus.FAILED,
                TaskStatus.SKIPPED,
                TaskStatus.CANCELLED,
                TaskStatus.STALE,
            ):
                return dependency_id
        raise RuntimeError("no failed dependency")

    def _record(self, kind: str, task_id: str | None = None, **data: Any) -> None:
        if self.trace is None:
            return
        self.trace.record(kind=kind, task_id=task_id, **data)
