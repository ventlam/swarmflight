from pathlib import Path

from swarmflight.runtime import TraceRecorder, load_trace, summarize_trace


def test_trace_roundtrip(tmp_path: Path):
    recorder = TraceRecorder()
    recorder.record("task_submitted", task_id="t-1", dependency_count=0)
    recorder.record("task_finished", task_id="t-1", ok=True)

    trace_file = tmp_path / "trace.jsonl"
    recorder.to_jsonl(trace_file)

    events = load_trace(trace_file)
    summary = summarize_trace(events)

    assert len(events) == 2
    assert events[0].kind == "task_submitted"
    assert events[1].kind == "task_finished"
    assert summary["total"] == 2
    assert summary["task_submitted"] == 1
    assert summary["task_finished"] == 1
