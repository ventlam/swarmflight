from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class RuntimeEvent:
    run_id: str
    timestamp: str
    kind: str
    task_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


RuntimeEventSubscriber = Callable[[RuntimeEvent], None]


class RuntimeEventBus:
    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or uuid4().hex
        self._events: list[RuntimeEvent] = []
        self._subscribers: list[RuntimeEventSubscriber] = []

    def publish(
        self,
        *,
        kind: str,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RuntimeEvent:
        event = RuntimeEvent(
            run_id=self.run_id,
            timestamp=datetime.now(UTC).isoformat(),
            kind=kind,
            task_id=task_id,
            payload=dict(payload or {}),
        )
        self._events.append(event)

        for subscriber in list(self._subscribers):
            try:
                subscriber(event)
            except Exception:  # noqa: BLE001 - subscriber isolation boundary
                continue

        return event

    def subscribe(self, subscriber: RuntimeEventSubscriber) -> None:
        self._subscribers.append(subscriber)

    @property
    def events(self) -> list[RuntimeEvent]:
        return list(self._events)
