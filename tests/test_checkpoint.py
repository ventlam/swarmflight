from pathlib import Path

from swarmflight.runtime import FunctionWorker, Orchestrator, RunCheckpointStore, TaskStatus


def _flaky_worker(task):
    fail_until_attempt = int(task.payload.get("fail_until_attempt", 0))
    if task.attempts <= fail_until_attempt:
        raise RuntimeError("transient")
    return {"task_id": task.task_id, "attempt": task.attempts}


def test_checkpoint_roundtrip_and_resume(tmp_path: Path):
    checkpoint_file = tmp_path / "run.checkpoint.json"
    store = RunCheckpointStore()

    orchestrator = Orchestrator(run_id="run-checkpoint-test")
    orchestrator.register_worker(FunctionWorker("worker-a", _flaky_worker))

    root = orchestrator.submit_task(
        "root",
        payload={"fail_until_attempt": 1},
        max_retries=1,
    )
    child = orchestrator.submit_task(
        "child",
        dependencies=[root.task_id],
    )

    first_tick = orchestrator.run_tick()
    assert len(first_tick) == 1
    assert orchestrator.get_task(root.task_id).status is TaskStatus.PENDING
    assert orchestrator.get_task(root.task_id).attempts == 1
    assert orchestrator.tick_count() == 1
    assert orchestrator.active_tick_count() == 1
    assert orchestrator.average_parallelism() == 1.0

    orchestrator.save_checkpoint(checkpoint_file, metadata={"kind": "unit-test"}, store=store)

    resumed = Orchestrator()
    resumed.register_worker(FunctionWorker("worker-a", _flaky_worker))
    resumed.load_checkpoint(store.load(checkpoint_file))
    assert resumed.tick_count() == 1
    assert resumed.active_tick_count() == 1
    assert resumed.average_parallelism() == 1.0

    resumed.run_all()

    assert resumed.run_id == "run-checkpoint-test"
    assert resumed.get_task(root.task_id).status is TaskStatus.COMPLETED
    assert resumed.get_task(root.task_id).attempts == 2
    assert resumed.get_task(child.task_id).status is TaskStatus.COMPLETED
    assert resumed.average_parallelism() >= 1.0
