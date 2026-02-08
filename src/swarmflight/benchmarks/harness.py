from __future__ import annotations

from pathlib import Path
from time import perf_counter

from swarmflight.benchmarks.models import (
    BenchmarkModeMetrics,
    BenchmarkReport,
    TaskSpec,
    TuningResult,
)
from swarmflight.benchmarks.policy import ContextualEpsilonGreedy
from swarmflight.benchmarks.scenarios import build_scenario_specs
from swarmflight.runtime import FunctionWorker, Orchestrator, Task, TaskStatus, TraceRecorder


def run_synthetic_benchmark(
    *,
    scenario: str = "wide",
    width: int = 8,
    swarm_workers: int = 4,
    max_retries: int = 1,
    trace_dir: str | Path | None = None,
) -> BenchmarkReport:
    if width < 1:
        raise ValueError("width must be >= 1")
    if swarm_workers < 1:
        raise ValueError("swarm_workers must be >= 1")
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")

    specs = build_scenario_specs(scenario=scenario, width=width)
    modes = {
        "single": _run_mode(
            mode="single",
            specs=specs,
            worker_count=1,
            max_retries=max_retries,
            trace_dir=trace_dir,
        ),
        "swarm": _run_mode(
            mode="swarm",
            specs=specs,
            worker_count=swarm_workers,
            max_retries=max_retries,
            trace_dir=trace_dir,
        ),
    }

    return BenchmarkReport(
        scenario=f"{scenario}-search-synthetic",
        width=width,
        max_retries=max_retries,
        modes=modes,
    )


def tune_parallelism(
    *,
    scenario: str = "wide",
    widths: list[int] | tuple[int, ...] = (4, 8, 12),
    episodes: int = 12,
    worker_arms: list[int] | tuple[int, ...] = (1, 2, 4, 6),
    max_retries: int = 1,
    epsilon: float = 0.2,
) -> TuningResult:
    if episodes < 1:
        raise ValueError("episodes must be >= 1")
    if not widths:
        raise ValueError("widths must not be empty")

    planner = ContextualEpsilonGreedy(arms=list(worker_arms), epsilon=epsilon)

    for _ in range(episodes):
        for width in widths:
            context = f"{scenario}:{width}"
            workers = planner.select(context)
            report = run_synthetic_benchmark(
                scenario=scenario,
                width=width,
                swarm_workers=workers,
                max_retries=max_retries,
            )
            metrics = report.modes["swarm"]
            reward = _reward(metrics)
            planner.update(context, workers, reward)

    recommendations = {width: planner.best_arm(f"{scenario}:{width}") for width in widths}
    return TuningResult(
        scenario=scenario,
        widths=tuple(widths),
        episodes=episodes,
        recommendations=recommendations,
    )


def format_tuning_report(result: TuningResult) -> str:
    lines = [
        f"scenario={result.scenario} episodes={result.episodes}",
        "width  recommended_workers",
    ]
    for width in result.widths:
        lines.append(f"{width:>5} {result.recommendations[width]:>20}")
    return "\n".join(lines)


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


def _run_mode(
    *,
    mode: str,
    specs: list[TaskSpec],
    worker_count: int,
    max_retries: int,
    trace_dir: str | Path | None,
) -> BenchmarkModeMetrics:
    trace_recorder = TraceRecorder() if trace_dir is not None else None
    orchestrator = Orchestrator(trace_recorder=trace_recorder)

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

    if trace_recorder is not None:
        assert trace_dir is not None
        output_dir = Path(trace_dir)
        trace_recorder.to_jsonl(output_dir / f"{mode}.jsonl")

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


def _reward(metrics: BenchmarkModeMetrics) -> float:
    return (
        1000.0 * metrics.pass_rate
        - float(metrics.critical_steps)
        - (0.001 * metrics.token_cost)
        - (2.0 * metrics.retry_count)
    )
