import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "scripts")

import run_daily_archive_loop as archive_loop


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=["fake"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def make_config(tmp_path, **overrides):
    values = {
        "list_url": "https://cafe.naver.com/example?boardType=L",
        "limit": 10,
        "interval_seconds": 600,
        "duration_hours": 24,
        "max_runs": 1,
        "stop_on_failed": 0,
        "python": "python-test",
        "log_dir": tmp_path / "logs",
    }
    values.update(overrides)
    return archive_loop.LoopConfig(**values)


def test_builds_daily_archive_execute_command_with_url_and_limit(tmp_path):
    config = make_config(tmp_path, limit=7)

    command = archive_loop.build_daily_archive_command(config)

    assert command[0] == "python-test"
    assert command[1].endswith(str(Path("scripts") / "daily_archive.py"))
    assert command[2:] == [
        "--execute",
        "--limit",
        "7",
        "--list-url",
        "https://cafe.naver.com/example?boardType=L",
    ]


def test_default_max_runs_is_calculated_from_duration_and_interval():
    assert archive_loop.calculate_max_runs(24, 600) == 144
    assert archive_loop.calculate_max_runs(1, 700) == 6


def test_loop_runs_max_runs_and_writes_log(tmp_path):
    calls = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stdout="failed     : 0\nsaved      : 1\n")

    slept = []
    config = make_config(tmp_path, max_runs=2, interval_seconds=5)

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=slept.append)

    assert rc == 0
    assert len(calls) == 2
    assert slept == [5]
    log_files = list((tmp_path / "logs").glob("*.log"))
    assert len(log_files) == 1
    log_text = log_files[0].read_text(encoding="utf-8")
    assert "run_number: 1" in log_text
    assert "run_number: 2" in log_text
    assert "stdout_summary:" in log_text


def test_nonzero_return_code_stops_loop(tmp_path):
    calls = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stderr="boom", returncode=3)

    config = make_config(tmp_path, max_runs=3)

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=lambda _seconds: None)

    assert rc == 1
    assert len(calls) == 1
    log_text = next((tmp_path / "logs").glob("*.log")).read_text(encoding="utf-8")
    assert "non-zero exit code 3" in log_text


def test_block_signal_in_stdout_stops_loop(tmp_path):
    calls = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stdout="login required\nfailed     : 0\n")

    config = make_config(tmp_path, max_runs=3)

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=lambda _seconds: None)

    assert rc == 0
    assert len(calls) == 1
    log_text = next((tmp_path / "logs").glob("*.log")).read_text(encoding="utf-8")
    assert "block signal detected: login" in log_text


def test_block_signal_in_stderr_stops_loop(tmp_path):
    calls = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stderr="CAPTCHA page", stdout="failed     : 0\n")

    config = make_config(tmp_path, max_runs=3)

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=lambda _seconds: None)

    assert rc == 0
    assert len(calls) == 1
    log_text = next((tmp_path / "logs").glob("*.log")).read_text(encoding="utf-8")
    assert "block signal detected: captcha" in log_text


def test_failed_count_above_threshold_stops_loop(tmp_path):
    calls = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stdout="failed     : 1\n")

    config = make_config(tmp_path, max_runs=3, stop_on_failed=0)

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=lambda _seconds: None)

    assert rc == 0
    assert len(calls) == 1
    log_text = next((tmp_path / "logs").glob("*.log")).read_text(encoding="utf-8")
    assert "failed count 1 exceeded threshold 0" in log_text


def test_placeholder_url_refuses_to_run(tmp_path):
    calls = []
    config = make_config(tmp_path, list_url="실제_URL", max_runs=1)

    rc = archive_loop.run_loop(config, runner=lambda command, **_kwargs: calls.append(command))

    assert rc == 2
    assert calls == []
    assert not (tmp_path / "logs").exists()


def test_main_placeholder_url_exits_before_subprocess(tmp_path, monkeypatch):
    monkeypatch.setattr(
        archive_loop.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    rc = archive_loop.main(
        [
            "--list-url",
            "YOUR_URL",
            "--max-runs",
            "1",
            "--log-dir",
            str(tmp_path / "logs"),
        ]
    )

    assert rc == 2
    assert not (tmp_path / "logs").exists()
