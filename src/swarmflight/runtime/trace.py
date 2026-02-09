from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class TraceEvent:
    run_id: str
    timestamp: str
    kind: str
    task_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class TraceRecorder:
    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or uuid4().hex
        self._events: list[TraceEvent] = []

    def record(self, kind: str, task_id: str | None = None, **data: Any) -> None:
        event = TraceEvent(
            run_id=self.run_id,
            timestamp=datetime.now(UTC).isoformat(),
            kind=kind,
            task_id=task_id,
            data=data,
        )
        self._events.append(event)

    @property
    def events(self) -> list[TraceEvent]:
        return list(self._events)

    def to_jsonl(self, path: str | Path) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(asdict(event), ensure_ascii=True) for event in self._events]
        output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def load_trace(path: str | Path) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        events.append(
            TraceEvent(
                run_id=item.get("run_id", ""),
                timestamp=item.get("timestamp", ""),
                kind=item.get("kind", ""),
                task_id=item.get("task_id"),
                data=item.get("data", {}),
            )
        )
    return events


def summarize_trace(events: list[TraceEvent]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for event in events:
        summary[event.kind] = summary.get(event.kind, 0) + 1
    summary["total"] = len(events)
    return summary
