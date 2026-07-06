import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
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
        "lock_file": tmp_path / "state" / "archive_loop.lock",
        "db_file": tmp_path / "data" / "archive.db",
        "lock_stale_minutes": 30,
        "market_schedule": False,
        "interactive_login": False,
        "realtime_index": False,
        "stop_after_empty_pages": 5,
        "argv_summary": "test argv",
    }
    values.update(overrides)
    return archive_loop.LoopConfig(**values)


def test_redact_secrets_masks_naver_session_cookies():
    text = "  - cookie: NID_AUT=abc123DEF; NID_SES=xyz789; NNB=FOO; keep=this"
    red = archive_loop.redact_secrets(text)
    assert "abc123DEF" not in red and "xyz789" not in red
    assert "NID_AUT=<redacted>" in red and "NID_SES=<redacted>" in red
    assert "keep=this" in red  # 비밀 아닌 값은 유지


def test_append_log_redacts_session_cookies(tmp_path):
    config = make_config(tmp_path)
    now = datetime(2026, 7, 6, 9, 0, 0)
    result = archive_loop.RunResult(
        run_number=1,
        started_at=now,
        finished_at=now,
        returncode=1,
        stdout="[STOP] member_api_request_failed: cookie: NID_AUT=LIVE_SECRET; NID_SES=LIVE_SES",
        stderr="",
        commands=[["python", "x"]],
        before_article_count=1,
        after_article_count=1,
        latest_article_id=100,
    )
    path = archive_loop.append_log(config, result)
    content = path.read_text(encoding="utf-8")
    assert "LIVE_SECRET" not in content and "LIVE_SES" not in content
    assert "NID_AUT=<redacted>" in content


def write_lock(path, *, updated_at=None, pid=99999):
    timestamp = updated_at or datetime.now().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "pid": pid,
                "started_at": timestamp,
                "updated_at": timestamp,
                "command": "existing loop",
                "lock_version": archive_loop.LOCK_VERSION,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def create_archive_db(path, *, article_count=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, article_id INTEGER)")
        conn.executemany(
            "INSERT INTO articles (article_id) VALUES (?)",
            [(1000 + i,) for i in range(article_count)],
        )


def make_preflight_config(tmp_path, **overrides):
    project_root = tmp_path / "project"
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True)
    index_tail_path = scripts_dir / "index_tail.py"
    batch_recollect_path = scripts_dir / "batch_recollect.py"
    index_tail_path.write_text("# test index tail\n", encoding="utf-8")
    batch_recollect_path.write_text("# test batch recollect\n", encoding="utf-8")
    db_file = project_root / "data" / "archive.db"
    create_archive_db(db_file, article_count=1)
    backups_dir = project_root / "backups"
    backups_dir.mkdir()
    values = {
        "project_root": project_root,
        "index_tail_path": index_tail_path,
        "batch_recollect_path": batch_recollect_path,
        "db_file": db_file,
        "backups_dir": backups_dir,
        "state_dir": project_root / "state",
        "log_dir": project_root / "logs" / "archive_loop",
        "reports_dir": project_root / "reports",
        "lock_file": project_root / "state" / "archive_loop.lock",
        "status_file": project_root / "state" / "archive_loop_status.json",
        "lock_stale_minutes": 30,
        "market_schedule": False,
    }
    values.update(overrides)
    return archive_loop.PreflightConfig(**values)


def test_builds_proven_archive_cycle_commands(tmp_path):
    config = make_config(tmp_path, limit=7)

    commands = archive_loop.build_archive_cycle_commands(config)

    assert commands[0] == [
        "python-test",
        str(archive_loop.PROJECT_ROOT / "scripts" / "index_tail.py"),
        "https://cafe.naver.com/example?boardType=L",
        "--collect-after-snapshot",
    ]
    assert commands[1] == [
        "python-test",
        str(archive_loop.PROJECT_ROOT / "scripts" / "batch_recollect.py"),
    ]


def test_proven_archive_cycle_preserves_existing_script_browser_behavior(tmp_path):
    config = make_config(tmp_path)

    commands = archive_loop.build_archive_cycle_commands(config)
    flattened = [part for command in commands for part in command]

    assert "--headed" not in flattened
    assert "--browser-profile-dir" not in flattened


def test_interactive_login_is_passed_to_index_tail_only(tmp_path):
    config = make_config(tmp_path, interactive_login=True)

    commands = archive_loop.build_archive_cycle_commands(config)

    assert commands[0][-1] == "--interactive-login"
    assert "--interactive-login" not in commands[1]


def test_realtime_index_uses_realtime_script_for_title_indexing_only(tmp_path):
    config = make_config(tmp_path, interactive_login=True, realtime_index=True, stop_after_empty_pages=5)

    commands = archive_loop.build_archive_cycle_commands(config)

    assert commands[0] == [
        "python-test",
        str(archive_loop.PROJECT_ROOT / "scripts" / "index_tail_realtime.py"),
        "https://cafe.naver.com/example?boardType=L",
        "--collect-after-snapshot",
        "--interactive-login",
        "--stop-after-empty-pages",
        "5",
    ]
    assert commands[1] == [
        "python-test",
        str(archive_loop.PROJECT_ROOT / "scripts" / "batch_recollect.py"),
    ]


def test_realtime_index_cli_builds_realtime_command(monkeypatch):
    captured = {}

    def fake_run_loop(config):
        captured["commands"] = archive_loop.build_archive_cycle_commands(config)
        return 0

    monkeypatch.setattr(archive_loop, "run_loop", fake_run_loop)

    rc = archive_loop.main(
        [
            "--list-url",
            "https://cafe.naver.com/example",
            "--interactive-login",
            "--realtime-index",
            "--stop-after-empty-pages",
            "5",
        ]
    )

    assert rc == 0
    assert captured["commands"][0][1].endswith(str(Path("scripts") / "index_tail_realtime.py"))
    assert captured["commands"][0][-2:] == ["--stop-after-empty-pages", "5"]
    assert captured["commands"][1][1].endswith(str(Path("scripts") / "batch_recollect.py"))


def test_default_max_runs_is_calculated_from_duration_and_interval():
    assert archive_loop.calculate_max_runs(24, 600) == 144
    assert archive_loop.calculate_max_runs(1, 700) == 6


def test_market_schedule_is_inactive_at_2330_until_0600():
    decision = archive_loop.market_schedule_decision(datetime(2026, 5, 31, 23, 30))

    assert decision.active is False
    assert decision.interval_seconds == 23400
    assert decision.label == "market-closed-23-06"


def test_market_schedule_uses_30_minutes_at_0630():
    decision = archive_loop.market_schedule_decision(datetime(2026, 5, 31, 6, 30))

    assert decision.active is True
    assert decision.interval_seconds == 1800


def test_market_schedule_uses_10_minutes_at_0730():
    decision = archive_loop.market_schedule_decision(datetime(2026, 5, 31, 7, 30))

    assert decision.active is True
    assert decision.interval_seconds == 600


def test_market_schedule_uses_5_minutes_at_0900():
    decision = archive_loop.market_schedule_decision(datetime(2026, 5, 31, 9, 0))

    assert decision.active is True
    assert decision.interval_seconds == 300


def test_market_schedule_uses_10_minutes_at_1700():
    decision = archive_loop.market_schedule_decision(datetime(2026, 5, 31, 17, 0))

    assert decision.active is True
    assert decision.interval_seconds == 600
    assert decision.label == "market-16-18-10m"


def test_market_schedule_uses_30_minutes_at_1900():
    decision = archive_loop.market_schedule_decision(datetime(2026, 5, 31, 19, 0))

    assert decision.active is True
    assert decision.interval_seconds == 1800
    assert decision.label == "market-18-23-30m"


def test_fixed_schedule_keeps_interval_seconds(tmp_path):
    config = make_config(tmp_path, interval_seconds=42, market_schedule=False)

    decision = archive_loop.schedule_decision_for(config, datetime(2026, 5, 31, 23, 30))

    assert decision.active is True
    assert decision.interval_seconds == 42
    assert decision.label == "fixed-interval"


def test_market_schedule_inactive_skips_collection_and_sleeps_until_active(tmp_path):
    calls = []
    slept = []
    config = make_config(tmp_path, market_schedule=True, max_runs=2)

    rc = archive_loop.run_loop(
        config,
        runner=lambda command, **_kwargs: calls.append(command),
        sleeper=slept.append,
        clock=lambda: datetime(2026, 5, 31, 23, 30),
    )

    assert rc == 0
    assert calls == []
    assert slept == [23400]
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["schedule_mode"] == "market"
    assert status["next_interval_seconds"] == 23400
    assert status["last_schedule_active"] is False
    assert status["last_schedule_label"] == "market-closed-23-06"


def test_market_schedule_interactive_login_waits_without_extra_login_when_inactive(tmp_path):
    calls = []
    slept = []
    config = make_config(tmp_path, market_schedule=True, interactive_login=True, max_runs=2)

    rc = archive_loop.run_loop(
        config,
        runner=lambda command, **_kwargs: calls.append(command),
        sleeper=slept.append,
        clock=lambda: datetime(2026, 5, 31, 23, 30),
    )

    assert rc == 0
    assert calls == []
    assert slept == [23400]
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["last_schedule_active"] is False
    assert status["stop_reason"] == "max runs completed"


def test_market_schedule_active_interactive_login_runs_proven_cycle_only(tmp_path, capsys):
    calls = []
    config = make_config(tmp_path, market_schedule=True, interactive_login=True, max_runs=1)

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return completed(stdout="failed     : 0\n")

    rc = archive_loop.run_loop(
        config,
        runner=fake_runner,
        sleeper=lambda _seconds: None,
        clock=lambda: datetime(2026, 5, 31, 9, 12),
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert len(calls) == 2
    assert calls[0][0][1].endswith(str(Path("scripts") / "index_tail.py"))
    assert calls[0][0][-1] == "--interactive-login"
    assert calls[1][0][1].endswith(str(Path("scripts") / "batch_recollect.py"))
    assert not any(command[1].endswith(str(Path("scripts") / "daily_archive.py")) for command, _ in calls)
    assert "daily_archive.py" not in captured.out
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["last_schedule_active"] is True
    assert status["last_schedule_label"] == "market-08-16-5m"
    assert status["stop_reason"] == "max runs completed"


def test_market_schedule_active_uses_time_window_interval_with_max_runs(tmp_path):
    calls = []
    slept = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stdout="failed     : 0\n")

    config = make_config(tmp_path, market_schedule=True, max_runs=2)

    rc = archive_loop.run_loop(
        config,
        runner=fake_runner,
        sleeper=slept.append,
        clock=lambda: datetime(2026, 5, 31, 9, 0),
    )

    assert rc == 0
    assert len(calls) == 4
    assert slept == [300]
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["schedule_mode"] == "market"
    assert status["next_interval_seconds"] == 300
    assert status["last_schedule_active"] is True
    assert status["last_schedule_label"] == "market-08-16-5m"


def test_loop_runs_max_runs_and_writes_log(tmp_path):
    calls = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stdout="failed     : 0\nsaved      : 1\n")

    slept = []
    config = make_config(tmp_path, max_runs=2, interval_seconds=5)

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=slept.append)

    assert rc == 0
    assert len(calls) == 4
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
    assert status["schedule_mode"] == "fixed"
    assert status["next_interval_seconds"] == 5
    assert status["is_running"] is False
    assert status["stop_reason"] == "max runs completed"
    assert not config.lock_file.exists()


def test_loop_starts_when_lock_file_is_missing(tmp_path):
    calls = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stdout="failed     : 0\nsaved      : 1\n")

    config = make_config(tmp_path, max_runs=1)

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=lambda _seconds: None)

    assert rc == 0
    assert len(calls) == 2
    assert not config.lock_file.exists()


def test_valid_lock_file_blocks_duplicate_loop(tmp_path, capsys):
    calls = []
    config = make_config(tmp_path, max_runs=1)
    write_lock(config.lock_file)

    rc = archive_loop.run_loop(
        config,
        runner=lambda command, **_kwargs: calls.append(command),
        sleeper=lambda _seconds: None,
    )

    captured = capsys.readouterr()
    assert rc == 3
    assert calls == []
    assert "another archive loop appears to be running" in captured.out
    assert config.lock_file.exists()


def test_stale_lock_file_can_be_taken_over(tmp_path, capsys):
    calls = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stdout="failed     : 0\nsaved      : 1\n")

    config = make_config(tmp_path, max_runs=1, lock_stale_minutes=30)
    write_lock(config.lock_file, updated_at=(datetime.now() - timedelta(minutes=31)).isoformat())

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=lambda _seconds: None)

    captured = capsys.readouterr()
    assert rc == 0
    assert len(calls) == 2
    assert "taking over stale lock file" in captured.out
    assert not config.lock_file.exists()


def test_corrupt_lock_file_can_be_taken_over(tmp_path, capsys):
    calls = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stdout="failed     : 0\nsaved      : 1\n")

    config = make_config(tmp_path, max_runs=1)
    config.lock_file.parent.mkdir(parents=True, exist_ok=True)
    config.lock_file.write_text("{not-json", encoding="utf-8")

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=lambda _seconds: None)

    captured = capsys.readouterr()
    assert rc == 0
    assert len(calls) == 2
    assert "taking over corrupt lock file" in captured.out
    assert not config.lock_file.exists()


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
    assert status["stop_reason"] == "archive cycle returned non-zero exit code 3"
    assert status["last_run_warning"] == "archive cycle returned non-zero exit code 3"
    assert status["last_return_code"] == 3


def test_block_signal_in_stdout_stops_loop(tmp_path):
    calls = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stdout="[DEBUG] login_required detected\nfailed     : 0\n")

    config = make_config(tmp_path, max_runs=3)

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=lambda _seconds: None)

    assert rc == 0
    assert len(calls) == 1
    log_text = next((tmp_path / "logs").glob("*.log")).read_text(encoding="utf-8")
    assert "block signal detected: login" in log_text
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["is_running"] is False
    assert status["stop_reason"] == "block signal detected: login"
    assert status["last_run_warning"] == "block signal detected: login"


def test_private_cafe_badge_in_stdout_does_not_stop_loop(tmp_path):
    calls = []
    slept = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stdout="비공개카페\nfailed     : 0\n")

    config = make_config(tmp_path, max_runs=2, interval_seconds=5)

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=slept.append)

    assert rc == 0
    assert len(calls) == 4
    assert slept == [5]
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["is_running"] is False
    assert status["stop_reason"] == "max runs completed"
    assert status["last_run_warning"] is None


def test_block_signal_in_stderr_stops_loop(tmp_path):
    calls = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stderr="[DEBUG] captcha detected", stdout="failed     : 0\n")

    config = make_config(tmp_path, max_runs=3)

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=lambda _seconds: None)

    assert rc == 0
    assert len(calls) == 1
    log_text = next((tmp_path / "logs").glob("*.log")).read_text(encoding="utf-8")
    assert "block signal detected: captcha" in log_text


def test_completed_recollect_cycle_ignores_earlier_login_debug(tmp_path):
    calls = []
    slept = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        if command[1].endswith(str(Path("scripts") / "index_tail.py")):
            return completed(
                stdout=(
                    "[DEBUG] login_required detected: no article-list markers found\n"
                    "[LOGIN] manual login completed\n"
                    "[index_tail] complete. total 0\n"
                )
            )
        return completed(stdout="[batch] no INDEXED articles\nfailed     : 0\n")

    config = make_config(tmp_path, max_runs=2, interval_seconds=5, interactive_login=True)

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=slept.append)

    assert rc == 0
    assert len(calls) == 4
    assert slept == [5]
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["stop_reason"] == "max runs completed"
    assert status["last_run_warning"] is None


def test_failed_count_at_threshold_stops_loop(tmp_path):
    calls = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return completed(stdout="failed     : 1\n")

    config = make_config(tmp_path, max_runs=3, stop_on_failed=1)

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=lambda _seconds: None)

    assert rc == 0
    assert len(calls) == 2
    log_text = next((tmp_path / "logs").glob("*.log")).read_text(encoding="utf-8")
    assert "failed count 1 exceeded threshold 1" in log_text
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["last_failed"] == 1
    assert status["stop_reason"] == "failed count 1 exceeded threshold 1"
    assert status["last_run_warning"] == "failed count 1 exceeded threshold 1"


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
    assert status["schedule_mode"] == "fixed"
    assert status["next_interval_seconds"] == 600
    assert status["duration_hours"] == 24
    assert status["limit"] == 10
    assert status["last_run_started_at"]
    assert status["last_run_finished_at"]
    assert status["last_return_code"] == 0
    assert status["last_saved"] == 2
    assert status["last_duplicates"] == 3
    assert status["last_failed"] == 0
    assert status["last_run_warning"] is None
    assert status["last_report_path"] == "C:\\reports\\daily.md"
    assert status["is_running"] is False
    assert status["stop_reason"] == "max runs completed"
    assert status["list_url_hash"] == archive_loop.list_url_hash(full_url)
    assert status["list_url_preview"] != full_url
    assert full_url not in config.status_file.read_text(encoding="utf-8")


def test_status_uses_archive_db_delta_and_latest_article_id_when_output_has_no_summary(tmp_path):
    config = make_config(tmp_path, max_runs=1)
    create_archive_db(config.db_file, article_count=2)

    def fake_runner(command, **_kwargs):
        if command[1].endswith(str(Path("scripts") / "index_tail.py")):
            with sqlite3.connect(config.db_file) as conn:
                conn.execute("INSERT INTO articles (article_id) VALUES (2000)")
        return completed(stdout="ok\n")

    rc = archive_loop.run_loop(config, runner=fake_runner, sleeper=lambda _seconds: None)

    assert rc == 0
    status = json.loads(config.status_file.read_text(encoding="utf-8"))
    assert status["last_saved"] == 1
    assert status["last_latest_article_id"] == 2000


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
    lock_file = tmp_path / "state" / "archive_loop.lock"
    write_lock(lock_file)
    status_file.write_text(
        json.dumps(
            {
                "started_at": "2026-05-30T09:00:00",
                "updated_at": "2026-05-30T09:10:00",
                "current_run": 2,
                "max_runs": 144,
                "interval_seconds": 600,
                "schedule_mode": "market",
                "next_interval_seconds": 300,
                "last_schedule_label": "market-08-16-5m",
                "last_schedule_active": True,
                "last_schedule_skipped_at": None,
                "duration_hours": 24,
                "limit": 10,
                "list_url_preview": "https://cafe.naver.com/example...",
                "last_run_started_at": "2026-05-30T09:00:00",
                "last_run_finished_at": "2026-05-30T09:01:00",
                "last_return_code": 0,
                "last_saved": 1,
                "last_duplicates": 2,
                "last_failed": 0,
                "last_latest_article_id": 169913,
                "last_run_warning": None,
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
    assert "schedule_mode: market" in captured.out
    assert "next_interval_seconds: 300" in captured.out
    assert "last_schedule_label: market-08-16-5m" in captured.out
    assert "last_schedule_active: yes" in captured.out
    assert "last_schedule_skipped_at: -" in captured.out
    assert "duration_hours: 24" in captured.out
    assert "limit: 10" in captured.out
    assert "list_url_preview: https://cafe.naver.com/example..." in captured.out
    assert "last_run_started_at: 2026-05-30T09:00:00" in captured.out
    assert "last_run_finished_at: 2026-05-30T09:01:00" in captured.out
    assert "last_return_code: 0" in captured.out
    assert "last_saved: 1" in captured.out
    assert "last_duplicates: 2" in captured.out
    assert "last_failed: 0" in captured.out
    assert "last_latest_article_id: 169913" in captured.out
    assert "last_run_warning: -" in captured.out
    assert "last_report_path: reports/2026-05-30.md" in captured.out
    assert "stop_reason: -" in captured.out
    assert '"is_running"' not in captured.out
    assert lock_file.exists()


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


def test_help_does_not_require_lock(monkeypatch, capsys):
    monkeypatch.setattr(
        archive_loop,
        "acquire_lock",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not acquire lock")),
    )

    try:
        archive_loop.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("--help should exit through argparse")

    captured = capsys.readouterr()
    assert "--lock-stale-minutes" in captured.out
    assert "--market-schedule" in captured.out
    assert "--interactive-login" in captured.out
    assert "index_tail.py" in captured.out
    assert "batch_recollect.py" in captured.out


def test_preflight_returns_zero_when_required_files_are_ready(tmp_path, monkeypatch, capsys):
    config = make_preflight_config(tmp_path)
    monkeypatch.chdir(config.project_root)

    rc = archive_loop.run_preflight(config)

    captured = capsys.readouterr()
    assert rc == 0
    assert "[OK] working directory:" in captured.out
    assert "[OK] archive.db articles: count=1" in captured.out
    assert "[OK] index_tail.py:" in captured.out
    assert "[OK] batch_recollect.py:" in captured.out
    assert "[WARN] list-url: real collection still requires" in captured.out
    assert "[OK] proven collection path:" in captured.out
    assert "[OK] schedule mode: fixed" in captured.out
    assert "index_tail.py --collect-after-snapshot" in captured.out
    assert "does not add login or marker logic" in captured.out
    assert "[archive_loop] summary:" in captured.out
    assert config.state_dir.exists()
    assert config.log_dir.exists()
    assert config.reports_dir.exists()


def test_preflight_prints_market_schedule_when_enabled(tmp_path, monkeypatch, capsys):
    config = make_preflight_config(tmp_path, market_schedule=True)
    monkeypatch.chdir(config.project_root)

    rc = archive_loop.run_preflight(config)

    captured = capsys.readouterr()
    assert rc == 0
    assert "[OK] schedule mode: market" in captured.out
    assert "23:00-06:00 stop" in captured.out
    assert "08:00-16:00 5m" in captured.out
    assert "16:00-18:00 10m" in captured.out
    assert "18:00-23:00 30m" in captured.out


def test_preflight_fails_when_archive_db_is_missing(tmp_path, monkeypatch, capsys):
    config = make_preflight_config(tmp_path)
    config.db_file = config.project_root / "data" / "missing.db"
    monkeypatch.chdir(config.project_root)

    rc = archive_loop.run_preflight(config)

    captured = capsys.readouterr()
    assert rc == 2
    assert "[FAIL] archive.db: missing:" in captured.out


def test_preflight_fails_when_archive_db_has_no_articles(tmp_path, monkeypatch, capsys):
    config = make_preflight_config(tmp_path)
    config.db_file = config.project_root / "data" / "empty.db"
    create_archive_db(config.db_file, article_count=0)
    monkeypatch.chdir(config.project_root)

    rc = archive_loop.run_preflight(config)

    captured = capsys.readouterr()
    assert rc == 2
    assert "[FAIL] archive.db articles: count=0" in captured.out


def test_preflight_runs_with_current_lock_without_creating_or_removing_it(tmp_path, monkeypatch, capsys):
    config = make_preflight_config(tmp_path)
    write_lock(config.lock_file)
    before = config.lock_file.read_text(encoding="utf-8")
    monkeypatch.chdir(config.project_root)

    rc = archive_loop.run_preflight(config)

    captured = capsys.readouterr()
    assert rc == 0
    assert "current lock present" in captured.out
    assert config.lock_file.read_text(encoding="utf-8") == before


def test_preflight_reports_corrupt_lock_as_warning(tmp_path, monkeypatch, capsys):
    config = make_preflight_config(tmp_path)
    config.lock_file.parent.mkdir(parents=True, exist_ok=True)
    config.lock_file.write_text("{not-json", encoding="utf-8")
    monkeypatch.chdir(config.project_root)

    rc = archive_loop.run_preflight(config)

    captured = capsys.readouterr()
    assert rc == 0
    assert "[WARN] archive_loop.lock: corrupt lock file" in captured.out
    assert config.lock_file.read_text(encoding="utf-8") == "{not-json"


def test_preflight_prints_status_summary_when_status_file_exists(tmp_path, monkeypatch, capsys):
    config = make_preflight_config(tmp_path)
    config.status_file.parent.mkdir(parents=True, exist_ok=True)
    config.status_file.write_text(
        json.dumps(
            {
                "is_running": True,
                "updated_at": "2026-05-30T12:00:00",
                "stop_reason": "testing",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(config.project_root)

    rc = archive_loop.run_preflight(config)

    captured = capsys.readouterr()
    assert rc == 0
    assert "[OK] archive_loop_status.json: running=yes" in captured.out
    assert "updated_at=2026-05-30T12:00:00" in captured.out
    assert "stop_reason=testing" in captured.out


def test_preflight_does_not_call_execute_or_create_lock(tmp_path, monkeypatch):
    config = make_preflight_config(tmp_path)
    monkeypatch.chdir(config.project_root)
    monkeypatch.setattr(
        archive_loop.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not run subprocess")),
    )
    monkeypatch.setattr(
        archive_loop,
        "acquire_lock",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not acquire lock")),
    )

    rc = archive_loop.run_preflight(config)

    assert rc == 0
    assert not config.lock_file.exists()


def test_main_preflight_does_not_require_list_url(monkeypatch):
    monkeypatch.setattr(archive_loop, "run_preflight", lambda _config=None: 0)

    rc = archive_loop.main(["--preflight"])

    assert rc == 0
