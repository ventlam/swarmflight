from __future__ import annotations

from typing import Protocol

from swarmflight.runtime.actions import Action, ActionType, Observation


class Policy(Protocol):
    def choose(self, observation: Observation) -> Action:
        """Return the next orchestrator action."""


class HeuristicPolicy:
    """Simple baseline policy for orchestrator behavior."""

    def choose(self, observation: Observation) -> Action:
        if observation.ready_tasks > 0:
            return Action(ActionType.ASSIGN, {"strategy": "round_robin"})
        if observation.running_tasks > 0 or observation.blocked_tasks > 0:
            return Action(ActionType.JOIN, {"wait": True})
        return Action(ActionType.FINISH, {})
