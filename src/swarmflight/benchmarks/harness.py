from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from swarmflight.runtime import FunctionWorker, Orchestrator, Task, TaskStatus


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


@dataclass(slots=True)
class BenchmarkReport:
    scenario: str
    width: int
    max_retries: int
    modes: dict[str, BenchmarkModeMetrics]


def run_synthetic_benchmark(
    *,
    width: int = 8,
    swarm_workers: int = 4,
    max_retries: int = 1,
) -> BenchmarkReport:
    if width < 1:
        raise ValueError("width must be >= 1")
    if swarm_workers < 1:
        raise ValueError("swarm_workers must be >= 1")
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")

    specs = build_wide_search_specs(width=width)
    modes = {
        "single": _run_mode(
            mode="single",
            specs=specs,
            worker_count=1,
            max_retries=max_retries,
        ),
        "swarm": _run_mode(
            mode="swarm",
            specs=specs,
            worker_count=swarm_workers,
            max_retries=max_retries,
        ),
    }

    return BenchmarkReport(
        scenario="wide-search-synthetic",
        width=width,
        max_retries=max_retries,
        modes=modes,
    )


def format_report(report: BenchmarkReport) -> str:
    lines = [
        f"scenario={report.scenario} width={report.width} max_retries={report.max_retries}",
        "mode   workers  pass_rate  critical_steps  retries  token_cost  wall_ms",
    ]

    for mode_name in ("single", "swarm"):
        mode = report.modes[mode_name]
        lines.append(
            f"{mode.mode:<6} {mode.worker_count:>7} {mode.pass_rate:>9.2%}"
            f" {mode.critical_steps:>15} {mode.retry_count:>8}"
            f" {mode.token_cost:>11} {mode.wall_time_ms:>8.2f}"
        )

    single_steps = report.modes["single"].critical_steps
    swarm_steps = report.modes["swarm"].critical_steps
    speedup = (single_steps / swarm_steps) if swarm_steps else 0.0
    lines.append(f"estimated_step_speedup={speedup:.2f}x")
    return "\n".join(lines)


def build_wide_search_specs(width: int) -> list[TaskSpec]:
    specs: list[TaskSpec] = [
        TaskSpec(
            task_id="discover",
            description="Initial discovery",
            dependencies=(),
            duration=2,
            token_cost=120,
        )
    ]

    branch_ids: list[str] = []
    for index in range(width):
        task_id = f"branch-{index + 1}"
        branch_ids.append(task_id)
        specs.append(
            TaskSpec(
                task_id=task_id,
                description=f"Parallel branch {index + 1}",
                dependencies=("discover",),
                duration=3,
                token_cost=160,
                fail_until_attempt=1 if index == 0 else 0,
            )
        )

    specs.append(
        TaskSpec(
            task_id="synthesize",
            description="Synthesize branch outputs",
            dependencies=tuple(branch_ids),
            duration=2,
            token_cost=140,
        )
    )

    return specs


def _run_mode(
    *,
    mode: str,
    specs: list[TaskSpec],
    worker_count: int,
    max_retries: int,
) -> BenchmarkModeMetrics:
    orchestrator = Orchestrator()

    for index in range(worker_count):
        worker_id = f"{mode}-worker-{index + 1}"
        orchestrator.register_worker(FunctionWorker(worker_id=worker_id, handler=_worker_handler))

    for spec in specs:
        orchestrator.submit_task(
            task_id=spec.task_id,
            description=spec.description,
            dependencies=spec.dependencies,
            max_retries=max_retries,
            payload={
                "duration": spec.duration,
                "token_cost": spec.token_cost,
                "fail_until_attempt": spec.fail_until_attempt,
            },
        )

    start = perf_counter()
    orchestrator.run_all()
    wall_time_ms = (perf_counter() - start) * 1000

    tasks = orchestrator.list_tasks()
    completed = sum(task.status is TaskStatus.COMPLETED for task in tasks)
    failed = sum(task.status is TaskStatus.FAILED for task in tasks)
    skipped = sum(task.status is TaskStatus.SKIPPED for task in tasks)
    total_attempts = sum(task.attempts for task in tasks)
    terminal_count = completed + failed + skipped
    retry_count = max(total_attempts - terminal_count, 0)

    token_cost = sum(int(task.payload.get("token_cost", 0)) * task.attempts for task in tasks)
    critical_steps = _estimate_critical_steps(tasks=tasks, worker_count=worker_count)
    pass_rate = (completed / len(tasks)) if tasks else 0.0

    return BenchmarkModeMetrics(
        mode=mode,
        worker_count=worker_count,
        task_count=len(tasks),
        completed=completed,
        failed=failed,
        skipped=skipped,
        pass_rate=pass_rate,
        total_attempts=total_attempts,
        retry_count=retry_count,
        token_cost=token_cost,
        critical_steps=critical_steps,
        wall_time_ms=wall_time_ms,
    )


def _worker_handler(task: Task) -> dict[str, int | str]:
    fail_until_attempt = int(task.payload.get("fail_until_attempt", 0))
    if task.attempts <= fail_until_attempt:
        raise RuntimeError(f"simulated failure on attempt {task.attempts}")

    return {
        "task_id": task.task_id,
        "attempt": task.attempts,
        "duration": int(task.payload.get("duration", 1)),
        "token_cost": int(task.payload.get("token_cost", 0)),
    }


def _estimate_critical_steps(tasks: list[Task], worker_count: int) -> int:
    executed = [task for task in tasks if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)]
    if not executed:
        return 0

    durations: dict[str, int] = {
        task.task_id: int(task.payload.get("duration", 1)) * max(task.attempts, 1)
        for task in executed
    }
    dependencies: dict[str, tuple[str, ...]] = {
        task.task_id: tuple(dep for dep in task.dependencies if dep in durations)
        for task in executed
    }

    finish_times: dict[str, int] = {}
    worker_available = [0] * worker_count
    remaining = set(durations)

    while remaining:
        ready = sorted(
            task_id
            for task_id in remaining
            if all(dep in finish_times for dep in dependencies[task_id])
        )
        if not ready:
            raise RuntimeError("unable to schedule benchmark tasks")

        for task_id in ready:
            worker_index = min(range(worker_count), key=worker_available.__getitem__)
            dependency_finish = max((finish_times[dep] for dep in dependencies[task_id]), default=0)
            start = max(worker_available[worker_index], dependency_finish)
            end = start + max(durations[task_id], 1)
            finish_times[task_id] = end
            worker_available[worker_index] = end
            remaining.remove(task_id)

    return max(finish_times.values(), default=0)
