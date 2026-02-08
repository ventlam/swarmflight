from swarmflight.runtime import FunctionWorker, Task


def test_function_worker_wraps_successful_handler():
    worker = FunctionWorker(
        worker_id="worker-a",
        handler=lambda task: {"echo": task.payload["value"]},
    )
    task = Task(task_id="task-1", description="Echo", payload={"value": "ok"})

    result = worker.run(task)

    assert result.ok is True
    assert result.worker_id == "worker-a"
    assert result.attempt == 1
    assert result.output == {"echo": "ok"}
    assert result.error is None


def test_function_worker_wraps_exceptions_as_failures():
    def failing_handler(_: Task) -> dict[str, str]:
        raise RuntimeError("boom")

    worker = FunctionWorker(worker_id="worker-b", handler=failing_handler)
    task = Task(task_id="task-2", description="Failing task")

    result = worker.run(task)

    assert result.ok is False
    assert result.worker_id == "worker-b"
    assert result.attempt == 1
    assert result.output == {}
    assert result.error == "boom"
