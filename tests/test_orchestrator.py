import threading
import time

import pytest

from swarmflight.runtime import (
    ConcurrencyLimits,
    FunctionWorker,
    Orchestrator,
    TaskStatus,
    TraceRecorder,
)


def test_orchestrator_runs_tasks_round_robin():
    orchestrator = Orchestrator()
    orchestrator.register_worker(FunctionWorker("worker-a", lambda _: {"worker": "worker-a"}))
    orchestrator.register_worker(FunctionWorker("worker-b", lambda _: {"worker": "worker-b"}))

    task_one = orchestrator.submit_task("Task one")
    task_two = orchestrator.submit_task("Task two")

    first_result = orchestrator.run_next()
    second_result = orchestrator.run_next()

    assert first_result is not None
    assert second_result is not None
    assert first_result.worker_id == "worker-a"
    assert second_result.worker_id == "worker-b"
    assert orchestrator.get_task(task_one.task_id).status is TaskStatus.COMPLETED
    assert orchestrator.get_task(task_two.task_id).status is TaskStatus.COMPLETED


def test_orchestrator_requires_registered_workers():
    orchestrator = Orchestrator()
    task = orchestrator.submit_task("Task without workers")

    with pytest.raises(RuntimeError, match="no workers registered"):
        orchestrator.run_task(task.task_id)


def test_orchestrator_rejects_duplicate_worker_ids():
    orchestrator = Orchestrator()
    worker = FunctionWorker("worker-a", lambda _: {"ok": True})
    orchestrator.register_worker(worker)

    with pytest.raises(ValueError, match="worker already registered"):
        orchestrator.register_worker(worker)


def test_orchestrator_unblocks_task_graph_dependencies():
    orchestrator = Orchestrator()
    orchestrator.register_worker(FunctionWorker("worker-a", lambda _: {"ok": True}))

    root = orchestrator.submit_task("root")
    child = orchestrator.submit_task("child", dependencies=[root.task_id])

    assert orchestrator.get_task(child.task_id).status is TaskStatus.PENDING

    orchestrator.run_all()

    assert orchestrator.get_task(root.task_id).status is TaskStatus.COMPLETED
    assert orchestrator.get_task(child.task_id).status is TaskStatus.COMPLETED


def test_orchestrator_skips_dependents_on_failed_dependency():
    orchestrator = Orchestrator()
    orchestrator.register_worker(FunctionWorker("worker-a", lambda _: {"ok": True}))
    orchestrator.register_worker(
        FunctionWorker("worker-b", lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    )

    failing = orchestrator.submit_task("failing", worker_id="worker-b")
    dependent = orchestrator.submit_task("dependent", dependencies=[failing.task_id])

    orchestrator.run_all()

    assert orchestrator.get_task(failing.task_id).status is TaskStatus.FAILED
    assert orchestrator.get_task(dependent.task_id).status is TaskStatus.SKIPPED
    dependent_result = orchestrator.result_for(dependent.task_id)
    assert dependent_result is not None
    assert dependent_result.error == f"dependency failed: {failing.task_id}"


def test_orchestrator_retries_then_completes():
    def flaky_handler(task):
        if task.attempts == 1:
            raise RuntimeError("transient")
        return {"attempt": task.attempts}

    orchestrator = Orchestrator()
    orchestrator.register_worker(FunctionWorker("worker-a", flaky_handler))

    task = orchestrator.submit_task("retry-task", max_retries=1)

    orchestrator.run_all()

    final_task = orchestrator.get_task(task.task_id)
    final_result = orchestrator.result_for(task.task_id)
    assert final_task.status is TaskStatus.COMPLETED
    assert final_task.attempts == 2
    assert final_result is not None
    assert final_result.ok is True
    assert final_result.attempt == 2


def test_orchestrator_emits_trace_events():
    trace = TraceRecorder()
    orchestrator = Orchestrator(trace_recorder=trace)
    orchestrator.register_worker(FunctionWorker("worker-a", lambda _: {"ok": True}))
    task = orchestrator.submit_task("tracked task")

    orchestrator.run_all()

    kinds = [event.kind for event in trace.events]
    assert all(event.run_id == orchestrator.run_id for event in trace.events)
    assert "worker_registered" in kinds
    assert "task_submitted" in kinds
    assert "policy_action" in kinds
    assert "task_attempt" in kinds
    assert orchestrator.get_task(task.task_id).status is TaskStatus.COMPLETED


def test_orchestrator_run_tick_executes_ready_tasks_in_parallel():
    counters = {"running": 0, "max_running": 0}
    lock = threading.Lock()

    def slow_handler(_):
        with lock:
            counters["running"] += 1
            counters["max_running"] = max(counters["max_running"], counters["running"])
        time.sleep(0.05)
        with lock:
            counters["running"] -= 1
        return {"ok": True}

    orchestrator = Orchestrator()
    orchestrator.register_worker(FunctionWorker("worker-a", slow_handler))
    orchestrator.register_worker(FunctionWorker("worker-b", slow_handler))
    orchestrator.submit_task("parallel-1")
    orchestrator.submit_task("parallel-2")

    attempts = orchestrator.run_tick()

    assert len(attempts) == 2
    assert counters["max_running"] >= 2


def test_orchestrator_respects_profile_concurrency_limit_per_tick():
    orchestrator = Orchestrator(concurrency_limits=ConcurrencyLimits(task_profiles={"cpu": 1}))
    orchestrator.register_worker(FunctionWorker("worker-a", lambda _: {"ok": True}, profile="cpu"))
    orchestrator.register_worker(FunctionWorker("worker-b", lambda _: {"ok": True}, profile="cpu"))

    first = orchestrator.submit_task("cpu-task-1", profile="cpu")
    second = orchestrator.submit_task("cpu-task-2", profile="cpu")

    first_tick = orchestrator.run_tick()

    assert len(first_tick) == 1
    first_task = orchestrator.get_task(first.task_id)
    second_task = orchestrator.get_task(second.task_id)
    assert first_task.status is TaskStatus.COMPLETED or second_task.status is TaskStatus.COMPLETED
    assert first_task.status is TaskStatus.PENDING or second_task.status is TaskStatus.PENDING

    second_tick = orchestrator.run_tick()
    assert len(second_tick) == 1
    assert orchestrator.get_task(first.task_id).status is TaskStatus.COMPLETED
    assert orchestrator.get_task(second.task_id).status is TaskStatus.COMPLETED


def test_orchestrator_marks_task_stale_after_queue_timeout():
    orchestrator = Orchestrator()
    orchestrator.register_worker(FunctionWorker("worker-a", lambda _: {"ok": True}))
    task = orchestrator.submit_task("stale-task", stale_timeout_ms=1)

    time.sleep(0.02)
    orchestrator.run_tick()

    final_task = orchestrator.get_task(task.task_id)
    result = orchestrator.result_for(task.task_id)
    assert final_task.status is TaskStatus.STALE
    assert result is not None
    assert result.error is not None
    assert "stale timeout" in result.error
