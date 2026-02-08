from swarmflight.cli import main


def test_version_flag(capsys):
    code = main(["--version"])
    captured = capsys.readouterr()

    assert code == 0
    assert captured.out.strip() == "swarmflight 0.1.0"
