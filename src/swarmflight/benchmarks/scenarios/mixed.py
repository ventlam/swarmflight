from __future__ import annotations

from swarmflight.benchmarks.models import TaskSpec


def build_mixed_search_specs(width: int) -> list[TaskSpec]:
    branch_count = max(width, 2)
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
    for index in range(branch_count):
        task_id = f"branch-{index + 1}"
        branch_ids.append(task_id)
        specs.append(
            TaskSpec(
                task_id=task_id,
                description=f"Branch {index + 1}",
                dependencies=("discover",),
                duration=2 + (index % 2),
                token_cost=140,
                fail_until_attempt=1 if index == 0 else 0,
            )
        )

    specs.append(
        TaskSpec(
            task_id="merge",
            description="Merge branch findings",
            dependencies=tuple(branch_ids),
            duration=2,
            token_cost=130,
        )
    )
    specs.append(
        TaskSpec(
            task_id="validate",
            description="Deep validation",
            dependencies=("merge",),
            duration=3,
            token_cost=160,
        )
    )
    specs.append(
        TaskSpec(
            task_id="finalize",
            description="Produce final answer",
            dependencies=("validate",),
            duration=2,
            token_cost=120,
        )
    )
    return specs
