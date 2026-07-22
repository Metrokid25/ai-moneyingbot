"""Read-only operational health check for the Archive collection bot.

The probe intentionally avoids ``COUNT(*)`` and ``saved_at`` predicates on the
large archive database.  It never starts/stops tasks, kills processes, opens a
browser, or writes state.  Windows-only scheduler/process probes degrade
gracefully so the DB/log portions remain useful in development environments.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

from run_daily_archive_loop import redact_secrets


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TASK_NAMES = (
    "Archive-CollectLoop",
    "Archive-Watchdog",
    "Archive-DailySummary",
)
KNOWN_PRESERVED_WORKTREE_ENTRY = "?? scripts/_step3_verify_v2.py"
ARCHIVE_PROCESS_MARKERS = (
    "run_daily_archive_loop.py",
    "index_tail_realtime.py",
    "batch_recollect.py",
)
_CYCLE_RE = re.compile(
    r"^\s*\[archive_loop\]\s+cycle\s+(?P<run>\d+)\s+finished:\s+"
    r"returncode=(?P<returncode>-?\d+)\s+saved_delta=(?P<saved>\d+)\s+"
    r"latest_id=(?P<latest>[^\s]+)",
    re.MULTILINE,
)
_FINISHED_AT_RE = re.compile(r"^finished_at:\s*(?P<timestamp>\S+)\s*$", re.MULTILINE)
_GENERAL_SECRET_RE = re.compile(
    r"(?i)\b(RAG_TELEGRAM_BOT_TOKEN|TELEGRAM_BOT_TOKEN|AUTHORIZATION)"
    r"(\s*[:=]\s*)(?:Bearer\s+)?[^\s;,\"']+"
)


@dataclass(frozen=True)
class Check:
    level: str
    name: str
    detail: str
    data: Any = None


@dataclass(frozen=True)
class HealthReport:
    verdict: str
    generated_at: str
    project_root: str
    checks: list[Check]


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
Sleeper = Callable[[float], None]


def _safe_detail(value: object, max_length: int = 500) -> str:
    text = redact_secrets(str(value))
    text = _GENERAL_SECRET_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", text)
    return text if len(text) <= max_length else f"{text[:max_length]}...<truncated>"


def _readonly_db_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}?mode=ro"


def probe_database(db_path: Path) -> Check:
    if not db_path.is_file():
        return Check("FAIL", "archive.db", f"missing: {db_path}")

    started = time.monotonic()
    try:
        with sqlite3.connect(_readonly_db_uri(db_path), uri=True, timeout=5) as conn:
            conn.execute("PRAGMA query_only = ON")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
            if "article_id" not in columns:
                return Check("FAIL", "archive.db", "articles.article_id is missing")
            row = conn.execute("SELECT MAX(article_id) FROM articles").fetchone()
    except sqlite3.Error as exc:
        return Check("FAIL", "archive.db", f"read-only MAX(article_id) failed: {type(exc).__name__}")

    elapsed_ms = round((time.monotonic() - started) * 1000)
    latest_id = int(row[0]) if row and row[0] is not None else None
    stat = db_path.stat()
    wal_path = Path(f"{db_path}-wal")
    data = {
        "latest_article_id": latest_id,
        "query_ms": elapsed_ms,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        "wal_exists": wal_path.is_file(),
    }
    if wal_path.is_file():
        wal_stat = wal_path.stat()
        data.update(
            {
                "wal_size_bytes": wal_stat.st_size,
                "wal_modified_at": datetime.fromtimestamp(wal_stat.st_mtime).astimezone().isoformat(),
            }
        )
    level = "OK" if latest_id is not None else "WARN"
    return Check(level, "archive.db", f"latest_article_id={latest_id}, query_ms={elapsed_ms}", data)


def observe_database(
    db_path: Path,
    initial: Check,
    seconds: float,
    *,
    sleeper: Sleeper = time.sleep,
) -> Check:
    if initial.level == "FAIL" or not isinstance(initial.data, dict):
        return Check("WARN", "database observation", "skipped because the initial DB probe failed")
    sleeper(seconds)
    final = probe_database(db_path)
    if final.level == "FAIL" or not isinstance(final.data, dict):
        return Check("WARN", "database observation", "final DB probe failed", final.data)

    before_id = initial.data.get("latest_article_id")
    after_id = final.data.get("latest_article_id")
    id_grew = isinstance(before_id, int) and isinstance(after_id, int) and after_id > before_id
    file_activity = any(
        initial.data.get(key) != final.data.get(key)
        for key in ("modified_at", "wal_modified_at", "size_bytes", "wal_size_bytes")
    )
    data = {
        "observe_seconds": seconds,
        "before_latest_article_id": before_id,
        "after_latest_article_id": after_id,
        "id_grew": id_grew,
        "db_or_wal_activity": file_activity,
    }
    level = "OK" if id_grew or file_activity else "INFO"
    return Check(
        level,
        "database observation",
        f"seconds={seconds:g}, latest_id={before_id}->{after_id}, "
        f"id_grew={id_grew}, db_or_wal_activity={file_activity}",
        data,
    )


def _read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__
    if not isinstance(value, dict):
        return None, "not_an_object"
    return value, None


def probe_status(status_path: Path) -> Check:
    value, error = _read_json_object(status_path)
    if value is None:
        return Check("WARN", "loop status", f"{error}: {status_path}")
    selected = {
        key: value.get(key)
        for key in (
            "updated_at",
            "is_running",
            "last_schedule_label",
            "last_return_code",
            "last_saved",
            "last_latest_article_id",
            "stop_reason",
        )
    }
    if selected["stop_reason"] is not None:
        selected["stop_reason"] = _safe_detail(selected["stop_reason"])
    level = "OK" if selected["is_running"] and selected["last_return_code"] in (None, 0) else "WARN"
    detail = (
        f"is_running={selected['is_running']}, updated_at={selected['updated_at']}, "
        f"last_return_code={selected['last_return_code']}, stop_reason={selected['stop_reason']}"
    )
    return Check(level, "loop status", detail, selected)


def probe_lock(lock_path: Path) -> Check:
    if not lock_path.exists():
        return Check("WARN", "loop lock", f"not present: {lock_path}")
    value, error = _read_json_object(lock_path)
    if value is None:
        return Check("WARN", "loop lock", f"unreadable ({error}): {lock_path}")
    selected = {key: value.get(key) for key in ("pid", "started_at", "updated_at", "lock_version")}
    return Check("OK", "loop lock", f"pid={selected['pid']}, updated_at={selected['updated_at']}", selected)


def probe_session_alert(state_path: Path) -> Check:
    if not state_path.exists():
        return Check("OK", "session alert", "no active alert state")
    value, error = _read_json_object(state_path)
    if value is None:
        return Check("WARN", "session alert", f"unreadable ({error}): {state_path}")
    selected = {key: value.get(key) for key in ("last_attempt_at", "last_alert_at")}
    return Check(
        "WARN",
        "session alert",
        f"alert state present: last_attempt_at={selected['last_attempt_at']}, "
        f"last_alert_at={selected['last_alert_at']}",
        selected,
    )


def _tail_text(path: Path, max_bytes: int = 2 * 1024 * 1024) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        raw = handle.read()
    return raw.decode("utf-8", errors="replace")


def _cycle_freshness_limit(now: datetime) -> timedelta:
    """Allow the intentional overnight stop plus a 06:00 catch-up grace period."""
    local_now = now.astimezone()
    if local_now.hour >= 23 or local_now.hour < 7:
        return timedelta(hours=10)
    return timedelta(hours=2)


def _parse_log_datetime(value: str, now: datetime) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now.astimezone().tzinfo)
    return parsed


def probe_recent_cycle(log_dir: Path, *, now: datetime | None = None) -> Check:
    now = now or datetime.now().astimezone()
    try:
        logs = sorted(
            (path for path in log_dir.glob("*.log") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError as exc:
        return Check("WARN", "recent cycle", f"log listing failed: {type(exc).__name__}")
    if not logs:
        return Check("WARN", "recent cycle", f"no logs: {log_dir}")

    log_path = None
    text = ""
    match = None
    for candidate in logs[:3]:
        try:
            candidate_text = _tail_text(candidate)
        except OSError as exc:
            return Check("WARN", "recent cycle", f"log read failed: {type(exc).__name__}")
        matches = list(_CYCLE_RE.finditer(candidate_text))
        if matches:
            log_path = candidate
            text = candidate_text
            match = matches[-1]
            break
    if log_path is None or match is None:
        return Check("WARN", "recent cycle", "no completed cycle marker in the latest 3 logs")

    finished_matches = [item for item in _FINISHED_AT_RE.finditer(text) if item.start() < match.start()]
    finished_at = (
        _parse_log_datetime(finished_matches[-1].group("timestamp"), now)
        if finished_matches
        else None
    )
    age_seconds = max(0, int((now - finished_at).total_seconds())) if finished_at else None
    freshness_limit = _cycle_freshness_limit(now)
    data = {
        "log_file": log_path.name,
        "log_modified_at": datetime.fromtimestamp(log_path.stat().st_mtime).astimezone().isoformat(),
        "finished_at": finished_at.isoformat() if finished_at else None,
        "age_seconds": age_seconds,
        "freshness_limit_seconds": int(freshness_limit.total_seconds()),
        "run": int(match.group("run")),
        "returncode": int(match.group("returncode")),
        "saved_delta": int(match.group("saved")),
        "latest_id": match.group("latest"),
    }
    fresh = age_seconds is not None and age_seconds <= freshness_limit.total_seconds()
    level = "OK" if data["returncode"] == 0 and fresh else "WARN"
    detail = (
        f"{data['log_file']}: run={data['run']}, returncode={data['returncode']}, "
        f"saved_delta={data['saved_delta']}, latest_id={data['latest_id']}, "
        f"finished_at={data['finished_at']}, age_seconds={age_seconds}"
    )
    return Check(level, "recent cycle", detail, data)


def _powershell_json(script: str, runner: CommandRunner = subprocess.run) -> tuple[Any, str | None]:
    try:
        completed = runner(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, type(exc).__name__
    if completed.returncode != 0:
        return None, f"powershell_exit_{completed.returncode}"
    try:
        return json.loads(completed.stdout), None
    except json.JSONDecodeError:
        return None, "invalid_powershell_json"


def probe_tasks(runner: CommandRunner = subprocess.run) -> list[Check]:
    names = ",".join(f"'{name}'" for name in TASK_NAMES)
    script = f"""
$rows = foreach ($name in @({names})) {{
  $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  if ($null -eq $task) {{
    [pscustomobject]@{{name=$name; found=$false; state=$null; last_run=$null; last_result=$null; next_run=$null}}
  }} else {{
    $info = Get-ScheduledTaskInfo -TaskName $name -ErrorAction SilentlyContinue
    [pscustomobject]@{{
      name=$name; found=$true; state=[string]$task.State
      last_run=if ($info) {{$info.LastRunTime.ToString('o')}} else {{$null}}
      last_result=if ($info) {{$info.LastTaskResult}} else {{$null}}
      next_run=if ($info) {{$info.NextRunTime.ToString('o')}} else {{$null}}
    }}
  }}
}}
@($rows) | ConvertTo-Json -Compress
"""
    value, error = _powershell_json(script, runner)
    if error:
        return [Check("WARN", "scheduled tasks", f"probe unavailable: {error}")]
    rows = value if isinstance(value, list) else [value]
    by_name = {row.get("name"): row for row in rows if isinstance(row, dict)}
    checks: list[Check] = []
    for name in TASK_NAMES:
        row = by_name.get(name)
        if not row or not row.get("found"):
            level = "FAIL" if name == "Archive-CollectLoop" else "WARN"
            checks.append(Check(level, f"task {name}", "not found", row))
            continue
        state = row.get("state")
        if name == "Archive-CollectLoop":
            level = "OK" if state == "Running" else "FAIL"
        else:
            last_result = row.get("last_result")
            state_ok = state in {"Ready", "Running"}
            result_ok = last_result in {None, 0, 267009}
            level = "OK" if state_ok and result_ok else "WARN"
        checks.append(
            Check(
                level,
                f"task {name}",
                f"state={state}, last_result={row.get('last_result')}, last_run={row.get('last_run')}",
                row,
            )
        )
    return checks


def probe_processes(runner: CommandRunner = subprocess.run) -> Check:
    script = r"""
$rows = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -in @('python.exe','pythonw.exe','chrome-headless-shell.exe') } |
  Select-Object @{n='pid';e={$_.ProcessId}}, @{n='parent_pid';e={$_.ParentProcessId}}, @{n='name';e={$_.Name}}, @{n='command_line';e={$_.CommandLine}})
ConvertTo-Json -InputObject $rows -Compress
"""
    value, error = _powershell_json(script, runner)
    if error:
        return Check("WARN", "archive processes", f"probe unavailable: {error}")
    rows = value if isinstance(value, list) else ([] if value is None else [value])
    archive_rows = []
    headless_count = 0
    controller_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").lower()
        command_line = str(row.get("command_line") or "")
        if name == "chrome-headless-shell.exe":
            headless_count += 1
            continue
        if any(marker.lower() in command_line.lower() for marker in ARCHIVE_PROCESS_MARKERS):
            markers = [marker for marker in ARCHIVE_PROCESS_MARKERS if marker.lower() in command_line.lower()]
            if "run_daily_archive_loop.py" in markers:
                controller_rows.append(row)
            archive_rows.append(
                {
                    "pid": row.get("pid"),
                    "parent_pid": row.get("parent_pid"),
                    "name": name,
                    "markers": markers,
                }
            )
    controller_pids = {row.get("pid") for row in controller_rows}
    controller_roots = [row for row in controller_rows if row.get("parent_pid") not in controller_pids]
    data = {
        "archive_python": archive_rows,
        "controller_process_count": len(controller_rows),
        "controller_instance_count": len(controller_roots),
        "headless_chrome_count": headless_count,
    }
    if not archive_rows:
        return Check("WARN", "archive processes", "no matching Archive python process", data)
    level = "OK" if len(controller_roots) == 1 else "WARN"
    return Check(
        level,
        "archive processes",
        f"archive_python={len(archive_rows)}, controller_processes={len(controller_rows)}, "
        f"controller_instances={len(controller_roots)}, headless_chrome={headless_count}",
        data,
    )


def probe_git(project_root: Path, runner: CommandRunner = subprocess.run) -> Check:
    def run_git(*args: str) -> tuple[str | None, str | None]:
        try:
            completed = runner(
                ["git", *args],
                cwd=project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return None, type(exc).__name__
        if completed.returncode != 0:
            return None, f"git_exit_{completed.returncode}"
        return completed.stdout.strip(), None

    head, error = run_git("rev-parse", "--short", "HEAD")
    if error:
        return Check("WARN", "git", f"probe unavailable: {error}")
    branch, _ = run_git("branch", "--show-current")
    status, status_error = run_git("status", "--porcelain=v1")
    if status_error:
        return Check("WARN", "git", f"status unavailable: {status_error}")
    entries = [line for line in (status or "").splitlines() if line]
    unexpected_entries = [line for line in entries if line != KNOWN_PRESERVED_WORKTREE_ENTRY]
    data = {
        "head": head,
        "branch": branch,
        "worktree_entry_count": len(entries),
        "unexpected_worktree_entries": unexpected_entries,
        "preserved_wip_present": KNOWN_PRESERVED_WORKTREE_ENTRY in entries,
    }
    level = "OK" if not unexpected_entries else "WARN"
    return Check(
        level,
        "git",
        f"branch={branch or '-'}, head={head}, worktree_entries={len(entries)}, "
        f"unexpected={len(unexpected_entries)}",
        data,
    )


def classify(checks: Sequence[Check]) -> str:
    collect_task = next((check for check in checks if check.name == "task Archive-CollectLoop"), None)
    if collect_task is not None and collect_task.level == "FAIL":
        return "STOPPED"
    live_catchup_evidence = _has_live_catchup_evidence(checks)
    actionable = [
        check
        for check in checks
        if check.level in {"WARN", "FAIL"}
        and not (live_catchup_evidence and _is_stale_successful_cycle(check))
    ]
    if actionable:
        return "DEGRADED"
    return "HEALTHY"


def _is_stale_successful_cycle(check: Check) -> bool:
    if check.name != "recent cycle" or not isinstance(check.data, dict):
        return False
    age = check.data.get("age_seconds")
    limit = check.data.get("freshness_limit_seconds")
    return (
        check.data.get("returncode") == 0
        and isinstance(age, int)
        and isinstance(limit, int)
        and age > limit
    )


def _has_live_catchup_evidence(checks: Sequence[Check]) -> bool:
    by_name = {check.name: check for check in checks}
    task = by_name.get("task Archive-CollectLoop")
    processes = by_name.get("archive processes")
    lock = by_name.get("loop lock")
    session = by_name.get("session alert")
    observation = by_name.get("database observation")
    return bool(
        task
        and task.level == "OK"
        and processes
        and processes.level == "OK"
        and isinstance(processes.data, dict)
        and processes.data.get("controller_instance_count") == 1
        and lock
        and lock.level == "OK"
        and session
        and session.level == "OK"
        and observation
        and observation.level == "OK"
    )


def run_healthcheck(
    project_root: Path = PROJECT_ROOT,
    *,
    include_system: bool = True,
    observe_seconds: float = 0,
    runner: CommandRunner = subprocess.run,
    sleeper: Sleeper = time.sleep,
) -> HealthReport:
    project_root = project_root.resolve()
    db_path = project_root / "data" / "archive.db"
    database_check = probe_database(db_path)
    checks = [
        probe_git(project_root, runner),
        database_check,
        probe_status(project_root / "state" / "archive_loop_status.json"),
        probe_lock(project_root / "state" / "archive_loop.lock"),
        probe_session_alert(project_root / "state" / "session_alert.json"),
        probe_recent_cycle(project_root / "logs" / "archive_loop"),
    ]
    if observe_seconds > 0:
        checks.append(observe_database(db_path, database_check, observe_seconds, sleeper=sleeper))
    if include_system:
        checks.extend(probe_tasks(runner))
        checks.append(probe_processes(runner))
    return HealthReport(
        verdict=classify(checks),
        generated_at=datetime.now().astimezone().isoformat(),
        project_root=str(project_root),
        checks=checks,
    )


def format_text(report: HealthReport) -> str:
    lines = [
        f"[Archive healthcheck] {report.verdict}",
        f"generated_at: {report.generated_at}",
        f"project_root: {report.project_root}",
    ]
    lines.extend(f"[{check.level}] {check.name}: {check.detail}" for check in report.checks)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Archive bot operational health check")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable JSON report")
    parser.add_argument(
        "--skip-system",
        action="store_true",
        help="skip Windows Scheduled Task and process probes",
    )
    parser.add_argument(
        "--observe-seconds",
        type=float,
        default=0,
        help="recheck MAX(article_id) and DB/WAL activity after this interval",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.observe_seconds < 0:
        raise SystemExit("--observe-seconds must be zero or positive")
    report = run_healthcheck(
        args.project_root,
        include_system=not args.skip_system,
        observe_seconds=args.observe_seconds,
    )
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print(format_text(report))
    return {"HEALTHY": 0, "DEGRADED": 1, "STOPPED": 2}[report.verdict]


if __name__ == "__main__":
    raise SystemExit(main())
