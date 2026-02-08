from swarmflight.benchmarks import run_synthetic_benchmark


def test_synthetic_benchmark_reports_swarm_step_advantage():
    report = run_synthetic_benchmark(width=6, swarm_workers=3, max_retries=1)

    single = report.modes["single"]
    swarm = report.modes["swarm"]

    assert single.task_count == 8
    assert swarm.task_count == 8
    assert single.retry_count == 1
    assert swarm.retry_count == 1
    assert single.pass_rate == 1.0
    assert swarm.pass_rate == 1.0
    assert swarm.critical_steps <= single.critical_steps


def test_synthetic_benchmark_without_retries_exposes_failures():
    report = run_synthetic_benchmark(width=4, swarm_workers=2, max_retries=0)

    single = report.modes["single"]
    swarm = report.modes["swarm"]

    assert single.failed >= 1
    assert swarm.failed >= 1
    assert single.pass_rate < 1.0
    assert swarm.pass_rate < 1.0
