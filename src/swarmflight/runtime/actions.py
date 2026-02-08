from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ActionType(StrEnum):
    FINISH = "finish"
    TOOL_CALL = "tool_call"
    SPAWN = "spawn"
    ASSIGN = "assign"
    JOIN = "join"
    REPLAN = "replan"


@dataclass(slots=True)
class Action:
    action_type: ActionType
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Observation:
    ready_tasks: int
    blocked_tasks: int
    running_tasks: int
    completed_tasks: int
    failed_tasks: int
    skipped_tasks: int
    workers: int
