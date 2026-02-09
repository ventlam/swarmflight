from swarmflight.runtime import (
    FunctionWorker,
    Orchestrator,
    OutputTruncationHook,
    RetryBackoffHook,
    RuntimeEventBus,
    StabilityGuardHook,
    TaskStatus,
)


def test_runtime_event_bus_collects_core_events():
    event_bus = RuntimeEventBus(run_id="run-events")
    orchestrator = Orchestrator(run_id="run-events", event_bus=event_bus, hooks=[])
    orchestrator.register_worker(FunctionWorker("worker-a", lambda _: {"ok": True}))
    task = orchestrator.submit_task("event-test")

    orchestrator.run_all()

    kinds = [event.kind for event in event_bus.events]
    assert "task_submitted" in kinds
    assert "task_scheduled" in kinds
    assert "task_attempt" in kinds
    assert "task_terminal" in kinds
    assert all(event.run_id == "run-events" for event in event_bus.events)
    assert orchestrator.get_task(task.task_id).status is TaskStatus.COMPLETED


def test_retry_backoff_hook_sleeps_before_requeue(monkeypatch):
    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("swarmflight.runtime.orchestrator.sleep", fake_sleep)

    def flaky(task):
        if task.attempts == 1:
            raise RuntimeError("transient")
        return {"ok": True}

    hook = RetryBackoffHook(base_delay_ms=50, max_delay_ms=50)
    orchestrator = Orchestrator(hooks=[hook])
    orchestrator.register_worker(FunctionWorker("worker-a", flaky))
    task = orchestrator.submit_task("backoff-test", max_retries=1)

    orchestrator.run_all()

    assert sleep_calls == [0.05]
    assert orchestrator.get_task(task.task_id).status is TaskStatus.COMPLETED


def test_output_truncation_hook_rewrites_large_payloads():
    hook = OutputTruncationHook(max_chars=64)
    orchestrator = Orchestrator(hooks=[hook])
    orchestrator.register_worker(FunctionWorker("worker-a", lambda _: {"blob": "x" * 512}))
    task = orchestrator.submit_task("truncate-test")

    orchestrator.run_all()

    result = orchestrator.result_for(task.task_id)
    assert result is not None
    assert result.output["__truncated__"] is True
    assert result.output["max_chars"] == 64
    assert result.output["original_chars"] > 64


def test_stability_guard_hook_emits_recovery_suggestion_on_retry_pressure():
    hook = StabilityGuardHook(retry_alert_threshold=1)
    orchestrator = Orchestrator(hooks=[hook])
    orchestrator.register_worker(
        FunctionWorker("worker-a", lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    )
    orchestrator.submit_task("unstable", max_retries=1)

    orchestrator.run_all()

    suggestions = [
        message
        for message in orchestrator.mailbox.drain("orchestrator")
        if message.kind == "stability_suggestion"
    ]
    assert suggestions
    assert suggestions[0].content["type"] == "retry_pressure"
