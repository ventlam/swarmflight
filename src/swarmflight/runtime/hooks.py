from __future__ import annotations

import json
from dataclasses import dataclass
from math import pow
from typing import Any

from swarmflight.runtime.events import RuntimeEvent
from swarmflight.runtime.mailbox import Mailbox
from swarmflight.runtime.models import Message, Task, TaskResult


class HookManager:
    def __init__(self, hooks: list[object] | None = None) -> None:
        self._hooks = list(hooks or [])

    @property
    def hooks(self) -> list[object]:
        return list(self._hooks)

    def before_task_attempt(self, task: Task, mailbox: Mailbox) -> None:
        for hook in self._hooks:
            callback = getattr(hook, "before_task_attempt", None)
            if callback is None:
                continue
            try:
                callback(task)
            except Exception as exc:  # noqa: BLE001 - hook isolation boundary
                self._report_hook_error(
                    mailbox=mailbox, hook=hook, method="before_task_attempt", error=exc
                )

    def after_task_attempt(self, task: Task, result: TaskResult, mailbox: Mailbox) -> TaskResult:
        current = result
        for hook in self._hooks:
            callback = getattr(hook, "after_task_attempt", None)
            if callback is None:
                continue
            try:
                next_result = callback(task, current)
                if next_result is not None:
                    current = next_result
            except Exception as exc:  # noqa: BLE001 - hook isolation boundary
                self._report_hook_error(
                    mailbox=mailbox, hook=hook, method="after_task_attempt", error=exc
                )
        return current

    def retry_delay_ms(self, task: Task, result: TaskResult, mailbox: Mailbox) -> int:
        max_delay = 0
        for hook in self._hooks:
            callback = getattr(hook, "retry_delay_ms", None)
            if callback is None:
                continue
            try:
                delay = int(callback(task, result))
                if delay > max_delay:
                    max_delay = delay
            except Exception as exc:  # noqa: BLE001 - hook isolation boundary
                self._report_hook_error(
                    mailbox=mailbox, hook=hook, method="retry_delay_ms", error=exc
                )
        return max(max_delay, 0)

    def on_event(self, event: RuntimeEvent, mailbox: Mailbox) -> None:
        for hook in self._hooks:
            callback = getattr(hook, "on_event", None)
            if callback is None:
                continue
            try:
                callback(event, mailbox)
            except Exception as exc:  # noqa: BLE001 - hook isolation boundary
                self._report_hook_error(mailbox=mailbox, hook=hook, method="on_event", error=exc)

    def _report_hook_error(
        self, *, mailbox: Mailbox, hook: object, method: str, error: Exception
    ) -> None:
        mailbox.send(
            Message(
                sender="hook_manager",
                recipient="orchestrator",
                kind="hook_error",
                content={
                    "hook": type(hook).__name__,
                    "method": method,
                    "error": str(error),
                },
            )
        )


@dataclass(slots=True)
class RetryBackoffHook:
    base_delay_ms: int = 5
    max_delay_ms: int = 1_000
    multiplier: float = 2.0

    def retry_delay_ms(self, task: Task, result: TaskResult) -> int:
        if result.ok:
            return 0
        attempt_index = max(task.attempts - 1, 0)
        delay = int(self.base_delay_ms * pow(self.multiplier, attempt_index))
        return min(delay, self.max_delay_ms)


@dataclass(slots=True)
class OutputTruncationHook:
    max_chars: int = 4_096

    def after_task_attempt(self, _: Task, result: TaskResult) -> TaskResult:
        serialized = json.dumps(result.output, ensure_ascii=True, sort_keys=True)
        if len(serialized) <= self.max_chars:
            return result

        result.output = {
            "__truncated__": True,
            "preview": serialized[: self.max_chars],
            "max_chars": self.max_chars,
            "original_chars": len(serialized),
        }
        return result


@dataclass(slots=True)
class StabilityGuardHook:
    retry_alert_threshold: int = 3
    stale_alert_threshold: int = 1
    stalled_tick_threshold: int = 3

    _retry_events: int = 0
    _stale_events: int = 0
    _stalled_ticks: int = 0
    _retry_alerted: bool = False
    _stale_alerted: bool = False
    _stall_alerted: bool = False

    def on_event(self, event: RuntimeEvent, mailbox: Mailbox) -> None:
        if event.kind == "task_retrying":
            self._retry_events += 1
            if self._retry_events >= self.retry_alert_threshold and not self._retry_alerted:
                self._retry_alerted = True
                self._emit_suggestion(
                    mailbox=mailbox,
                    run_id=event.run_id,
                    suggestion_type="retry_pressure",
                    message=(
                        "High retry pressure detected. Consider increasing worker count, "
                        "raising max_retries carefully, or adjusting retry backoff."
                    ),
                    details={"retry_events": self._retry_events},
                )
            return

        if event.kind == "task_stale":
            self._stale_events += 1
            if self._stale_events >= self.stale_alert_threshold and not self._stale_alerted:
                self._stale_alerted = True
                self._emit_suggestion(
                    mailbox=mailbox,
                    run_id=event.run_id,
                    suggestion_type="stale_tasks",
                    message=(
                        "Stale tasks detected. Consider increasing stale_timeout_ms, "
                        "reducing queue pressure, or adding worker capacity."
                    ),
                    details={"stale_events": self._stale_events},
                )
            return

        if event.kind == "tick_stalled":
            self._stalled_ticks += 1
            if self._stalled_ticks >= self.stalled_tick_threshold and not self._stall_alerted:
                self._stall_alerted = True
                self._emit_suggestion(
                    mailbox=mailbox,
                    run_id=event.run_id,
                    suggestion_type="scheduler_stall",
                    message=(
                        "No scheduling progress with ready tasks. Check worker/profile mapping "
                        "and concurrency limits for bottlenecks."
                    ),
                    details={"stalled_ticks": self._stalled_ticks},
                )
            return

        if event.kind in {"task_scheduled", "task_attempt", "task_terminal"}:
            self._stalled_ticks = 0
            self._stall_alerted = False

    def _emit_suggestion(
        self,
        *,
        mailbox: Mailbox,
        run_id: str,
        suggestion_type: str,
        message: str,
        details: dict[str, Any],
    ) -> None:
        mailbox.send(
            Message(
                sender="stability_guard",
                recipient="orchestrator",
                kind="stability_suggestion",
                content={
                    "run_id": run_id,
                    "type": suggestion_type,
                    "message": message,
                    **details,
                },
            )
        )


def default_runtime_hooks() -> list[object]:
    return [
        RetryBackoffHook(),
        OutputTruncationHook(),
        StabilityGuardHook(),
    ]
