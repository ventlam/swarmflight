from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(slots=True)
class ArmStats:
    pulls: int = 0
    value: float = 0.0


class ContextualEpsilonGreedy:
    def __init__(self, arms: list[int], epsilon: float = 0.2, seed: int = 42) -> None:
        if not arms:
            raise ValueError("arms must not be empty")
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon must be in [0, 1]")
        self._arms = list(dict.fromkeys(arms))
        self._epsilon = epsilon
        self._rng = random.Random(seed)
        self._stats: dict[str, dict[int, ArmStats]] = {}

    def select(self, context: str) -> int:
        context_stats = self._stats.setdefault(context, {arm: ArmStats() for arm in self._arms})
        untried = [arm for arm, stat in context_stats.items() if stat.pulls == 0]
        if untried:
            return self._rng.choice(untried)
        if self._rng.random() < self._epsilon:
            return self._rng.choice(self._arms)
        return max(self._arms, key=lambda arm: context_stats[arm].value)

    def update(self, context: str, arm: int, reward: float) -> None:
        context_stats = self._stats.setdefault(context, {key: ArmStats() for key in self._arms})
        stat = context_stats[arm]
        stat.pulls += 1
        stat.value += (reward - stat.value) / stat.pulls

    def best_arm(self, context: str) -> int:
        context_stats = self._stats.setdefault(context, {arm: ArmStats() for arm in self._arms})
        return max(self._arms, key=lambda arm: context_stats[arm].value)
