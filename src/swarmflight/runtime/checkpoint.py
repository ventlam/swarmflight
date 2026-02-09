from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from swarmflight.runtime.models import Task, TaskResult, TaskStatus


@dataclass(slots=True)
class RunCheckpoint:
    run_id: str
    created_at: str
    ready_queue: list[str]
    blocked: list[str]
    running: list[str]
    scheduler_cursor: int
    result_order: list[str]
    tasks: dict[str, dict[str, Any]]
    results: dict[str, dict[str, Any]]
    attempt_history: dict[str, list[dict[str, Any]]]
    tick_count: int = 0
    active_tick_count: int = 0
    scheduled_attempt_count: int = 0
    max_parallelism: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class RunCheckpointStore:
    def save(self, path: str | Path, checkpoint: RunCheckpoint) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": checkpoint.run_id,
            "created_at": checkpoint.created_at,
            "ready_queue": checkpoint.ready_queue,
            "blocked": checkpoint.blocked,
            "running": checkpoint.running,
            "scheduler_cursor": checkpoint.scheduler_cursor,
            "result_order": checkpoint.result_order,
            "tasks": checkpoint.tasks,
            "results": checkpoint.results,
            "attempt_history": checkpoint.attempt_history,
            "tick_count": checkpoint.tick_count,
            "active_tick_count": checkpoint.active_tick_count,
            "scheduled_attempt_count": checkpoint.scheduled_attempt_count,
            "max_parallelism": checkpoint.max_parallelism,
            "metadata": checkpoint.metadata,
        }
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        temp_path.replace(output_path)

    def load(self, path: str | Path) -> RunCheckpoint:
        source_path = Path(path)
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        return RunCheckpoint(
            run_id=str(payload.get("run_id", "")),
            created_at=str(payload.get("created_at", "")),
            ready_queue=[str(item) for item in payload.get("ready_queue", [])],
            blocked=[str(item) for item in payload.get("blocked", [])],
            running=[str(item) for item in payload.get("running", [])],
            scheduler_cursor=int(payload.get("scheduler_cursor", 0)),
            result_order=[str(item) for item in payload.get("result_order", [])],
            tasks={
                str(task_id): dict(task_payload)
                for task_id, task_payload in dict(payload.get("tasks", {})).items()
            },
            results={
                str(task_id): dict(result_payload)
                for task_id, result_payload in dict(payload.get("results", {})).items()
            },
            attempt_history={
                str(task_id): [dict(item) for item in items]
                for task_id, items in dict(payload.get("attempt_history", {})).items()
            },
            tick_count=int(payload.get("tick_count", 0)),
            active_tick_count=int(payload.get("active_tick_count", 0)),
            scheduled_attempt_count=int(payload.get("scheduled_attempt_count", 0)),
            max_parallelism=int(payload.get("max_parallelism", 0)),
            metadata=dict(payload.get("metadata", {})),
        )


def serialize_task(task: Task) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "description": task.description,
        "payload": task.payload,
        "dependencies": list(task.dependencies),
        "profile": task.profile,
        "provider": task.provider,
        "stale_timeout_ms": task.stale_timeout_ms,
        "max_runtime_ms": task.max_runtime_ms,
        "queued_at": _to_iso(task.queued_at),
        "started_at": _to_iso(task.started_at),
        "ended_at": _to_iso(task.ended_at),
        "max_retries": task.max_retries,
        "attempts": task.attempts,
        "worker_id": task.worker_id,
        "status": task.status.value,
    }


def deserialize_task(payload: dict[str, Any]) -> Task:
    return Task(
        task_id=str(payload.get("task_id", "")),
        description=str(payload.get("description", "")),
        payload=dict(payload.get("payload", {})),
        dependencies=tuple(str(item) for item in payload.get("dependencies", [])),
        profile=str(payload.get("profile", "default")),
        provider=_optional_str(payload.get("provider")),
        stale_timeout_ms=_optional_int(payload.get("stale_timeout_ms")),
        max_runtime_ms=_optional_int(payload.get("max_runtime_ms")),
        queued_at=_from_iso(_optional_str(payload.get("queued_at"))) or datetime.now(UTC),
        started_at=_from_iso(_optional_str(payload.get("started_at"))),
        ended_at=_from_iso(_optional_str(payload.get("ended_at"))),
        max_retries=int(payload.get("max_retries", 0)),
        attempts=int(payload.get("attempts", 0)),
        worker_id=_optional_str(payload.get("worker_id")),
        status=TaskStatus(str(payload.get("status", TaskStatus.PENDING.value))),
    )


def serialize_result(result: TaskResult) -> dict[str, Any]:
    return {
        "task_id": result.task_id,
        "worker_id": result.worker_id,
        "ok": result.ok,
        "attempt": result.attempt,
        "output": result.output,
        "error": result.error,
    }


def deserialize_result(payload: dict[str, Any]) -> TaskResult:
    return TaskResult(
        task_id=str(payload.get("task_id", "")),
        worker_id=str(payload.get("worker_id", "")),
        ok=bool(payload.get("ok", False)),
        attempt=int(payload.get("attempt", 1)),
        output=dict(payload.get("output", {})),
        error=_optional_str(payload.get("error")),
    )


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
