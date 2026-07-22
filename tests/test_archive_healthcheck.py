import json
import inspect
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, "scripts")

import archive_healthcheck as healthcheck


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=["fake"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def create_archive_db(path: Path, article_ids=(100, 105)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE articles (article_id INTEGER PRIMARY KEY, saved_at TEXT)")
        conn.executemany(
            "INSERT INTO articles(article_id, saved_at) VALUES (?, '2026-07-22')",
            [(article_id,) for article_id in article_ids],
        )


def test_probe_database_reads_max_id_without_writing(tmp_path):
    db_path = tmp_path / "archive.db"
    create_archive_db(db_path)
    before = db_path.stat().st_mtime_ns

    result = healthcheck.probe_database(db_path)

    assert result.level == "OK"
    assert result.data["latest_article_id"] == 105
    assert result.data["query_ms"] >= 0
    assert result.data["wal_exists"] is False
    assert db_path.stat().st_mtime_ns == before


def test_probe_database_source_forbids_large_table_scan_queries():
    source = inspect.getsource(healthcheck.probe_database)

    assert "COUNT(" not in source.upper()
    assert "SAVED_AT" not in source.upper()
    assert "MAX(article_id)" in source
    assert "PRAGMA query_only" in source


def test_observe_database_reports_growth_without_treating_no_growth_as_failure(tmp_path):
    db_path = tmp_path / "archive.db"
    create_archive_db(db_path, article_ids=(100,))
    initial = healthcheck.probe_database(db_path)

    def insert_article(_seconds):
        with sqlite3.connect(db_path) as conn:
            conn.execute("INSERT INTO articles(article_id, saved_at) VALUES (101, '2026-07-22')")

    grew = healthcheck.observe_database(db_path, initial, 1, sleeper=insert_article)
    unchanged = healthcheck.observe_database(db_path, healthcheck.probe_database(db_path), 1, sleeper=lambda _: None)

    assert grew.level == "OK"
    assert grew.data["id_grew"] is True
    assert unchanged.level == "INFO"
    assert unchanged.data["id_grew"] is False


def test_probe_database_rejects_missing_article_id(tmp_path):
    db_path = tmp_path / "archive.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY)")

    result = healthcheck.probe_database(db_path)

    assert result.level == "FAIL"
    assert "article_id is missing" in result.detail


def test_probe_recent_cycle_uses_only_original_anchored_cycle_line(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "2026-07-22.log").write_text(
        "finished_at: 2026-07-22T11:59:00+00:00\n"
        "stdout_summary: [archive_loop] cycle 99 finished: returncode=0 saved_delta=999 latest_id=999\n"
        "[archive_loop] cycle 3 finished: returncode=0 saved_delta=2 latest_id=172700\n",
        encoding="utf-8",
    )

    result = healthcheck.probe_recent_cycle(
        log_dir, now=datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    )

    assert result.level == "OK"
    assert result.data["run"] == 3
    assert result.data["saved_delta"] == 2
    assert result.data["latest_id"] == "172700"


def test_probe_recent_cycle_searches_previous_log_after_overnight_skip(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    previous = log_dir / "2026-07-21.log"
    previous.write_text(
        "finished_at: 2026-07-21T22:30:00+09:00\n"
        "[archive_loop] cycle 30 finished: returncode=0 saved_delta=0 latest_id=172700\n",
        encoding="utf-8",
    )
    latest = log_dir / "2026-07-22.log"
    latest.write_text("[archive_loop] schedule skip: market-23-06-stop\n", encoding="utf-8")
    latest.touch()

    result = healthcheck.probe_recent_cycle(
        log_dir, now=datetime.fromisoformat("2026-07-22T05:00:00+09:00")
    )

    assert result.level == "OK"
    assert result.data["log_file"] == "2026-07-21.log"
    assert result.data["run"] == 30


def test_probe_recent_cycle_warns_when_last_success_is_stale(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "2026-07-22.log").write_text(
        "finished_at: 2026-07-22T08:00:00+09:00\n"
        "[archive_loop] cycle 1 finished: returncode=0 saved_delta=0 latest_id=172700\n",
        encoding="utf-8",
    )

    result = healthcheck.probe_recent_cycle(
        log_dir, now=datetime.fromisoformat("2026-07-22T12:00:01+09:00")
    )

    assert result.level == "WARN"
    assert result.data["age_seconds"] > result.data["freshness_limit_seconds"]


def test_probe_status_exposes_only_operational_fields(tmp_path):
    path = tmp_path / "status.json"
    path.write_text(
        json.dumps(
            {
                "updated_at": "2026-07-22T12:00:00",
                "is_running": True,
                "last_return_code": 0,
                "last_latest_article_id": 172700,
                "list_url_preview": "must-not-be-returned",
                "stop_reason": (
                    "cookie NID_AUT=DO_NOT_LEAK "
                    "RAG_TELEGRAM_BOT_TOKEN=ALSO_SECRET "
                    "Authorization: Bearer THIRD_SECRET"
                ),
            }
        ),
        encoding="utf-8",
    )

    result = healthcheck.probe_status(path)

    assert result.level == "OK"
    assert "list_url_preview" not in result.data
    assert result.data["last_latest_article_id"] == 172700
    serialized = json.dumps(result.data)
    assert "DO_NOT_LEAK" not in serialized
    assert "ALSO_SECRET" not in serialized
    assert "THIRD_SECRET" not in serialized
    assert "NID_AUT=<redacted>" in result.data["stop_reason"]


def test_probe_session_alert_does_not_expose_detail(tmp_path):
    path = tmp_path / "session_alert.json"
    path.write_text(
        json.dumps(
            {
                "last_attempt_at": "2026-07-22T12:00:00",
                "last_alert_at": "2026-07-22T12:00:01",
                "last_detail": "cookie=NID_AUT=DO_NOT_LEAK",
            }
        ),
        encoding="utf-8",
    )

    result = healthcheck.probe_session_alert(path)

    serialized = json.dumps(result.data)
    assert result.level == "WARN"
    assert "DO_NOT_LEAK" not in serialized


def test_probe_git_accepts_only_the_known_preserved_wip(tmp_path):
    outputs = iter(["580cb23\n", "main\n", "?? scripts/_step3_verify_v2.py\n"])

    def runner(*args, **kwargs):
        return completed(stdout=next(outputs))

    result = healthcheck.probe_git(tmp_path, runner)

    assert result.level == "OK"
    assert result.data["preserved_wip_present"] is True
    assert result.data["unexpected_worktree_entries"] == []


def test_probe_tasks_marks_missing_collect_loop_as_fail():
    payload = [
        {"name": "Archive-CollectLoop", "found": False, "state": None},
        {"name": "Archive-Watchdog", "found": True, "state": "Ready", "last_result": 0},
        {"name": "Archive-DailySummary", "found": True, "state": "Ready", "last_result": 0},
    ]

    def runner(*args, **kwargs):
        return completed(stdout=json.dumps(payload))

    results = healthcheck.probe_tasks(runner)

    assert results[0].name == "task Archive-CollectLoop"
    assert results[0].level == "FAIL"
    assert healthcheck.classify(results) == "STOPPED"


def test_probe_processes_does_not_return_full_command_lines():
    payload = [
        {
            "pid": 10,
            "parent_pid": 1,
            "name": "python.exe",
            "command_line": "python scripts/run_daily_archive_loop.py --secret DO_NOT_LEAK",
        },
        {
            "pid": 11,
            "parent_pid": 10,
            "name": "chrome-headless-shell.exe",
            "command_line": "chrome --cookie=SECRET",
        },
    ]

    def runner(*args, **kwargs):
        return completed(stdout=json.dumps(payload))

    result = healthcheck.probe_processes(runner)

    serialized = json.dumps(result.data)
    assert result.level == "OK"
    assert result.data["controller_process_count"] == 1
    assert result.data["controller_instance_count"] == 1
    assert result.data["headless_chrome_count"] == 1
    assert "DO_NOT_LEAK" not in serialized
    assert "--cookie" not in serialized


def test_probe_processes_counts_venv_wrapper_pair_as_one_instance():
    payload = [
        {
            "pid": 10,
            "parent_pid": 1,
            "name": "python.exe",
            "command_line": "python scripts/run_daily_archive_loop.py",
        },
        {
            "pid": 11,
            "parent_pid": 10,
            "name": "python.exe",
            "command_line": "python scripts/run_daily_archive_loop.py",
        },
    ]

    result = healthcheck.probe_processes(lambda *args, **kwargs: completed(stdout=json.dumps(payload)))

    assert result.level == "OK"
    assert result.data["controller_process_count"] == 2
    assert result.data["controller_instance_count"] == 1


def test_probe_processes_warns_for_two_controller_instances():
    payload = [
        {
            "pid": 10,
            "parent_pid": 1,
            "name": "python.exe",
            "command_line": "python scripts/run_daily_archive_loop.py",
        },
        {
            "pid": 20,
            "parent_pid": 1,
            "name": "python.exe",
            "command_line": "python scripts/run_daily_archive_loop.py",
        },
    ]

    result = healthcheck.probe_processes(lambda *args, **kwargs: completed(stdout=json.dumps(payload)))

    assert result.level == "WARN"
    assert result.data["controller_instance_count"] == 2


def test_classify_warns_without_a_confirmed_stopped_collect_task():
    checks = [
        healthcheck.Check("OK", "archive.db", "ok"),
        healthcheck.Check("WARN", "recent cycle", "missing"),
    ]

    assert healthcheck.classify(checks) == "DEGRADED"


def test_classify_accepts_stale_successful_cycle_only_with_strong_live_catchup_evidence():
    stale_cycle = healthcheck.Check(
        "WARN",
        "recent cycle",
        "stale",
        {"returncode": 0, "age_seconds": 8000, "freshness_limit_seconds": 7200},
    )
    strong_evidence = [
        healthcheck.Check("OK", "task Archive-CollectLoop", "Running"),
        healthcheck.Check(
            "OK", "archive processes", "one", {"controller_instance_count": 1}
        ),
        healthcheck.Check("OK", "loop lock", "present"),
        healthcheck.Check("OK", "session alert", "clear"),
        healthcheck.Check("OK", "database observation", "activity"),
    ]

    assert healthcheck.classify([stale_cycle, *strong_evidence]) == "HEALTHY"
    assert healthcheck.classify([stale_cycle, *strong_evidence[:-1]]) == "DEGRADED"


def test_classify_never_masks_a_stale_failed_cycle():
    failed_cycle = healthcheck.Check(
        "WARN",
        "recent cycle",
        "failed",
        {"returncode": 1, "age_seconds": 8000, "freshness_limit_seconds": 7200},
    )
    strong_evidence = [
        healthcheck.Check("OK", "task Archive-CollectLoop", "Running"),
        healthcheck.Check(
            "OK", "archive processes", "one", {"controller_instance_count": 1}
        ),
        healthcheck.Check("OK", "loop lock", "present"),
        healthcheck.Check("OK", "session alert", "clear"),
        healthcheck.Check("OK", "database observation", "activity"),
    ]

    assert healthcheck.classify([failed_cycle, *strong_evidence]) == "DEGRADED"


def test_format_text_starts_with_verdict():
    report = healthcheck.HealthReport(
        verdict="HEALTHY",
        generated_at="2026-07-22T12:00:00+09:00",
        project_root="C:/repo",
        checks=[healthcheck.Check("OK", "archive.db", "latest_article_id=1")],
    )

    text = healthcheck.format_text(report)

    assert text.startswith("[Archive healthcheck] HEALTHY")
    assert "[OK] archive.db: latest_article_id=1" in text
