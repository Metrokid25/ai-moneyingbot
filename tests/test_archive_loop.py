import json
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
        "status_file": tmp_path / "state" / "archive_loop_status.json",
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
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["current_run"] == 2
    assert status["max_runs"] == 2
    assert status["is_running"] is False
    assert status["stop_reason"] == "max runs completed"


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
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["is_running"] is False
    assert status["stop_reason"] == "daily_archive returned non-zero exit code 3"
    assert status["last_return_code"] == 3


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
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["is_running"] is False
    assert status["stop_reason"] == "block signal detected: login"


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
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["last_failed"] == 1
    assert status["stop_reason"] == "failed count 1 exceeded threshold 0"


def test_status_file_tracks_summary_fields_and_redacts_url(tmp_path):
    full_url = "https://cafe.naver.com/example?boardType=L&clubid=123456&page=99"

    def fake_runner(_command, **_kwargs):
        return completed(
            stdout="\n".join(
                [
                    "  saved      : 2",
                    "  duplicates : 3",
                    "  failed     : 0",
                    "  report     : C:\\reports\\daily.md",
                ]
            )
        )

    config = make_config(tmp_path, list_url=full_url, max_runs=1)

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=lambda _seconds: None)

    assert rc == 0
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["started_at"]
    assert status["updated_at"]
    assert status["current_run"] == 1
    assert status["interval_seconds"] == 600
    assert status["duration_hours"] == 24
    assert status["limit"] == 10
    assert status["last_run_started_at"]
    assert status["last_run_finished_at"]
    assert status["last_return_code"] == 0
    assert status["last_saved"] == 2
    assert status["last_duplicates"] == 3
    assert status["last_failed"] == 0
    assert status["last_report_path"] == "C:\\reports\\daily.md"
    assert status["is_running"] is False
    assert status["stop_reason"] == "max runs completed"
    assert status["list_url_hash"] == archive_loop.list_url_hash(full_url)
    assert status["list_url_preview"] != full_url
    assert full_url not in config.status_file.read_text(encoding="utf-8")


def test_placeholder_url_refuses_to_run(tmp_path):
    calls = []
    config = make_config(tmp_path, list_url="실제_URL", max_runs=1)

    rc = archive_loop.run_loop(config, runner=lambda command, **_kwargs: calls.append(command))

    assert rc == 2
    assert calls == []
    assert not (tmp_path / "logs").exists()
    assert not config.status_file.exists()


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


def test_status_prints_existing_file_without_running_subprocess(tmp_path, monkeypatch, capsys):
    status_file = tmp_path / "status.json"
    status_file.write_text(
        json.dumps(
            {
                "started_at": "2026-05-30T09:00:00",
                "updated_at": "2026-05-30T09:10:00",
                "current_run": 2,
                "max_runs": 144,
                "interval_seconds": 600,
                "duration_hours": 24,
                "limit": 10,
                "list_url_preview": "https://cafe.naver.com/example...",
                "last_run_started_at": "2026-05-30T09:00:00",
                "last_run_finished_at": "2026-05-30T09:01:00",
                "last_return_code": 0,
                "last_saved": 1,
                "last_duplicates": 2,
                "last_failed": 0,
                "last_report_path": "reports/2026-05-30.md",
                "stop_reason": None,
                "is_running": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        archive_loop.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    rc = archive_loop.main(["--status", "--status-file", str(status_file)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "[archive_loop] status" in captured.out
    assert "running: no" in captured.out
    assert "started_at: 2026-05-30T09:00:00" in captured.out
    assert "updated_at: 2026-05-30T09:10:00" in captured.out
    assert "current_run / max_runs: 2 / 144" in captured.out
    assert "interval_seconds: 600" in captured.out
    assert "duration_hours: 24" in captured.out
    assert "limit: 10" in captured.out
    assert "list_url_preview: https://cafe.naver.com/example..." in captured.out
    assert "last_run_started_at: 2026-05-30T09:00:00" in captured.out
    assert "last_run_finished_at: 2026-05-30T09:01:00" in captured.out
    assert "last_return_code: 0" in captured.out
    assert "last_saved: 1" in captured.out
    assert "last_duplicates: 2" in captured.out
    assert "last_failed: 0" in captured.out
    assert "last_report_path: reports/2026-05-30.md" in captured.out
    assert "stop_reason: -" in captured.out
    assert '"is_running"' not in captured.out


def test_status_reports_missing_file_without_running_subprocess(tmp_path, monkeypatch, capsys):
    status_file = tmp_path / "missing.json"
    monkeypatch.setattr(
        archive_loop.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    rc = archive_loop.main(["--status", "--status-file", str(status_file)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "no status file" in captured.out
