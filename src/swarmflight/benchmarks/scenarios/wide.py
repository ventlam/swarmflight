from __future__ import annotations

from swarmflight.benchmarks.models import TaskSpec


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
