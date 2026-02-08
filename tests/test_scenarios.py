from swarmflight.benchmarks import (
    build_deep_search_specs,
    build_mixed_search_specs,
    build_scenario_specs,
    build_wide_search_specs,
)


def test_wide_scenario_has_merge_dependencies():
    specs = build_wide_search_specs(width=4)
    assert specs[0].task_id == "discover"
    assert specs[-1].task_id == "synthesize"
    assert len(specs[-1].dependencies) == 4


def test_deep_scenario_is_chain_like():
    specs = build_deep_search_specs(width=3)
    assert specs[0].dependencies == ()
    for spec in specs[1:]:
        assert len(spec.dependencies) == 1


def test_mixed_scenario_contains_parallel_and_serial_phases():
    specs = build_mixed_search_specs(width=5)
    task_ids = [spec.task_id for spec in specs]
    assert "merge" in task_ids
    assert "validate" in task_ids
    assert "finalize" in task_ids


def test_build_scenario_specs_rejects_unknown_scenario():
    try:
        build_scenario_specs(scenario="unknown", width=4)
    except ValueError as exc:
        assert "unsupported scenario" in str(exc)
    else:
        raise AssertionError("expected ValueError")
