from swarmflight.benchmarks import run_synthetic_benchmark, tune_parallelism


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


def test_deep_scenario_runs_successfully():
    report = run_synthetic_benchmark(scenario="deep", width=5, swarm_workers=3, max_retries=1)

    assert report.scenario == "deep-search-synthetic"
    assert report.modes["single"].task_count == report.modes["swarm"].task_count
    assert report.modes["swarm"].pass_rate == 1.0


def test_bandit_tuning_returns_recommendations():
    result = tune_parallelism(
        scenario="mixed",
        widths=[4, 6],
        episodes=4,
        worker_arms=[1, 2, 3],
        epsilon=0.1,
    )

    assert result.scenario == "mixed"
    assert result.recommendations.keys() == {4, 6}
    assert all(worker in {1, 2, 3} for worker in result.recommendations.values())
