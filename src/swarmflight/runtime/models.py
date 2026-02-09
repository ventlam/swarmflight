from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    STALE = "stale"


@dataclass(slots=True)
class Task:
    task_id: str
    description: str
    payload: dict[str, Any] = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()
    profile: str = "default"
    provider: str | None = None
    stale_timeout_ms: int | None = None
    max_runtime_ms: int | None = None
    queued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    ended_at: datetime | None = None
    max_retries: int = 0
    attempts: int = 0
    worker_id: str | None = None
    status: TaskStatus = TaskStatus.PENDING


@dataclass(slots=True)
class TaskResult:
    task_id: str
    worker_id: str
    ok: bool
    attempt: int = 1
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(slots=True)
class Message:
    sender: str
    recipient: str
    kind: str
    content: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
