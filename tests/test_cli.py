from swarmflight.cli import main


def test_version_flag(capsys):
    code = main(["--version"])
    captured = capsys.readouterr()

    assert code == 0
    assert captured.out.strip() == "swarmflight 0.2.0"


def test_bench_command_runs(capsys):
    code = main(["bench", "--width", "3", "--swarm-workers", "2", "--max-retries", "1"])
    captured = capsys.readouterr()

    assert code == 0
    assert "scenario=wide-search-synthetic" in captured.out
    assert "estimated_step_speedup=" in captured.out
