from swarmflight.benchmarks.models import TaskSpec
from swarmflight.benchmarks.scenarios.deep import build_deep_search_specs
from swarmflight.benchmarks.scenarios.mixed import build_mixed_search_specs
from swarmflight.benchmarks.scenarios.wide import build_wide_search_specs


def build_scenario_specs(scenario: str, width: int) -> list[TaskSpec]:
    if scenario == "wide":
        return build_wide_search_specs(width=width)
    if scenario == "deep":
        return build_deep_search_specs(width=width)
    if scenario == "mixed":
        return build_mixed_search_specs(width=width)
    raise ValueError(f"unsupported scenario: {scenario}")


__all__ = [
    "build_deep_search_specs",
    "build_mixed_search_specs",
    "build_scenario_specs",
    "build_wide_search_specs",
]
