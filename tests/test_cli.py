from swarmflight.cli import main


def test_version_flag(capsys):
    code = main(["--version"])
    captured = capsys.readouterr()

    assert code == 0
    assert captured.out.strip() == "swarmflight 0.3.0"


def test_bench_command_runs(capsys, tmp_path):
    code = main(
        [
            "bench",
            "--scenario",
            "wide",
            "--width",
            "3",
            "--swarm-workers",
            "2",
            "--max-retries",
            "1",
            "--trace-dir",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "scenario=wide-search-synthetic" in captured.out
    assert "avg_parallel" in captured.out
    assert "estimated_step_speedup=" in captured.out
    assert (tmp_path / "single.jsonl").exists()
    assert (tmp_path / "swarm.jsonl").exists()


def test_replay_command_runs(capsys, tmp_path):
    trace_file = tmp_path / "trace.jsonl"
    trace_file.write_text(
        '{"timestamp":"t","kind":"task_submitted","task_id":"a","data":{}}\n'
        '{"timestamp":"t","kind":"task_finished","task_id":"a","data":{"ok":true}}\n',
        encoding="utf-8",
    )

    code = main(["replay", str(trace_file)])
    captured = capsys.readouterr()

    assert code == 0
    assert "total=2" in captured.out
    assert "task_submitted=1" in captured.out
    assert "task_finished=1" in captured.out


def test_tune_command_runs(capsys):
    code = main(
        [
            "tune",
            "--scenario",
            "mixed",
            "--widths",
            "4,6",
            "--episodes",
            "3",
            "--worker-arms",
            "1,2",
            "--epsilon",
            "0.1",
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "scenario=mixed" in captured.out
    assert "recommended_workers" in captured.out


def test_resume_command_runs_from_checkpoint(capsys, tmp_path):
    checkpoint_file = tmp_path / "swarm.checkpoint.json"

    bench_code = main(
        [
            "bench",
            "--scenario",
            "mixed",
            "--width",
            "4",
            "--swarm-workers",
            "2",
            "--max-retries",
            "1",
            "--checkpoint-file",
            str(checkpoint_file),
            "--stop-after-ticks",
            "1",
        ]
    )
    _ = capsys.readouterr()

    assert bench_code == 0
    assert checkpoint_file.exists()

    resume_code = main(["resume", str(checkpoint_file)])
    captured = capsys.readouterr()

    assert resume_code == 0
    assert f"checkpoint={checkpoint_file}" in captured.out
    assert "mode=swarm" in captured.out
    assert "pass_rate=" in captured.out
    assert "avg_parallelism=" in captured.out
