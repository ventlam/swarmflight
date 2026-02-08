from __future__ import annotations

from swarmflight.benchmarks.models import TaskSpec


def build_deep_search_specs(width: int) -> list[TaskSpec]:
    depth = max(width + 2, 3)
    specs: list[TaskSpec] = []

    previous = "seed"
    specs.append(
        TaskSpec(
            task_id=previous,
            description="Seed query",
            dependencies=(),
            duration=2,
            token_cost=120,
        )
    )

    for index in range(1, depth):
        task_id = f"hop-{index}"
        specs.append(
            TaskSpec(
                task_id=task_id,
                description=f"Deep reasoning hop {index}",
                dependencies=(previous,),
                duration=3,
                token_cost=150,
                fail_until_attempt=1 if index == 2 else 0,
            )
        )
        previous = task_id

    specs.append(
        TaskSpec(
            task_id="finalize",
            description="Finalize deep-search answer",
            dependencies=(previous,),
            duration=2,
            token_cost=140,
        )
    )
    return specs
