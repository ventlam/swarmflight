from swarmflight.runtime import ConcurrencyLimits, ConcurrencyManager


def test_concurrency_manager_prefers_profile_limit_over_provider_and_default():
    manager = ConcurrencyManager(
        ConcurrencyLimits(
            task_profiles={"cpu": 1},
            providers={"openai": 2},
            default=3,
        )
    )

    first = manager.try_acquire(profile="cpu", provider="openai")
    second = manager.try_acquire(profile="cpu", provider="openai")

    assert first is not None
    assert second is None


def test_concurrency_manager_falls_back_to_provider_then_default():
    manager = ConcurrencyManager(
        ConcurrencyLimits(
            task_profiles={},
            providers={"openai": 1},
            default=2,
        )
    )

    first = manager.try_acquire(profile="default", provider="openai")
    second = manager.try_acquire(profile="default", provider="openai")

    assert first is not None
    assert second is None

    manager.release(first)

    third = manager.try_acquire(profile="default", provider="anthropic")
    fourth = manager.try_acquire(profile="default", provider="anthropic")
    fifth = manager.try_acquire(profile="default", provider="anthropic")

    assert third is not None
    assert fourth is not None
    assert fifth is None


def test_concurrency_manager_unbounded_when_limit_is_zero_or_missing():
    manager = ConcurrencyManager(ConcurrencyLimits(default=0))

    tokens = [manager.try_acquire(profile="default", provider=None) for _ in range(10)]

    assert all(token is not None for token in tokens)
