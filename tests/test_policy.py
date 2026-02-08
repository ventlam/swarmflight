from swarmflight.runtime import ActionType, HeuristicPolicy, Observation


def test_heuristic_policy_assigns_when_ready_tasks_exist():
    policy = HeuristicPolicy()
    action = policy.choose(
        Observation(
            ready_tasks=1,
            blocked_tasks=0,
            running_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            skipped_tasks=0,
            workers=2,
        )
    )

    assert action.action_type is ActionType.ASSIGN


def test_heuristic_policy_finishes_when_no_work_left():
    policy = HeuristicPolicy()
    action = policy.choose(
        Observation(
            ready_tasks=0,
            blocked_tasks=0,
            running_tasks=0,
            completed_tasks=2,
            failed_tasks=0,
            skipped_tasks=0,
            workers=2,
        )
    )

    assert action.action_type is ActionType.FINISH
