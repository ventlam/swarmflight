from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TaskSpec:
    task_id: str
    description: str
    dependencies: tuple[str, ...]
    duration: int
    token_cost: int
    fail_until_attempt: int = 0


@dataclass(slots=True)
class BenchmarkModeMetrics:
    mode: str
    worker_count: int
    task_count: int
    completed: int
    failed: int
    skipped: int
    pass_rate: float
    total_attempts: int
    retry_count: int
    token_cost: int
    critical_steps: int
    wall_time_ms: float
    stale_count: int = 0
    avg_parallelism: float = 0.0


@dataclass(slots=True)
class BenchmarkReport:
    scenario: str
    width: int
    max_retries: int
    modes: dict[str, BenchmarkModeMetrics]


@dataclass(slots=True)
class TuningResult:
    scenario: str
    widths: tuple[int, ...]
    episodes: int
    recommendations: dict[int, int]
