"""Run the proven archive indexing/recollection scripts on a fixed interval.

Each loop pass delegates to the existing successful archive path:
`scripts/index_tail.py <list-url> --collect-after-snapshot`, followed by
`scripts/batch_recollect.py`. The wrapper does not parse Naver pages or
perform collection directly.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Callable, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DEFAULT_INTERVAL_SECONDS = 600
DEFAULT_DURATION_HOURS = 24.0
DEFAULT_LIMIT = 10
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs" / "archive_loop"
DEFAULT_STATUS_FILE = PROJECT_ROOT / "state" / "archive_loop_status.json"
DEFAULT_LOCK_FILE = PROJECT_ROOT / "state" / "archive_loop.lock"
DEFAULT_DB_FILE = PROJECT_ROOT / "data" / "archive.db"
DEFAULT_BACKUPS_DIR = PROJECT_ROOT / "backups"
DEFAULT_STATE_DIR = PROJECT_ROOT / "state"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "reports"
DEFAULT_LOCK_STALE_MINUTES = 30.0
LOCK_VERSION = 1
BLOCK_SIGNAL_PATTERNS = (
    ("captcha", re.compile(r"\[DEBUG\].*captcha.*detected|captcha detected", re.IGNORECASE)),
    ("login", re.compile(r"\blogin_required\b|redirected to login url|password_input_found=true", re.IGNORECASE)),
    ("permission", re.compile(r"permission denied|permission block|권한이 없습니다|접근 권한이 없습니다")),
    ("block", re.compile(r"\[STOP\].*차단|block detected|blocked by", re.IGNORECASE)),
    ("verification", re.compile(r"본인인증.*detected|identity verification detected", re.IGNORECASE)),
)
PLACEHOLDER_PATTERNS = (
    "<",
    ">",
    "여기에",
    "실제_URL",
    "YOUR_URL",
)


@dataclass
class LoopConfig:
    list_url: str
    limit: int = DEFAULT_LIMIT
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    duration_hours: float = DEFAULT_DURATION_HOURS
    max_runs: int | None = None
    stop_on_failed: int = 0
    python: str = sys.executable
    log_dir: Path = DEFAULT_LOG_DIR
    status_file: Path = DEFAULT_STATUS_FILE
    lock_file: Path = DEFAULT_LOCK_FILE
    db_file: Path = DEFAULT_DB_FILE
    lock_stale_minutes: float = DEFAULT_LOCK_STALE_MINUTES
    market_schedule: bool = False
    interactive_login: bool = False
    realtime_index: bool = False
    stop_after_empty_pages: int = 5
    argv_summary: str = ""


@dataclass
class RunResult:
    run_number: int
    started_at: datetime
    finished_at: datetime
    returncode: int
    stdout: str
    stderr: str
    commands: list[list[str]]
    before_article_count: int | None = None
    after_article_count: int | None = None
    latest_article_id: int | None = None


@dataclass
class PreflightConfig:
    project_root: Path = PROJECT_ROOT
    index_tail_path: Path = PROJECT_ROOT / "scripts" / "index_tail.py"
    batch_recollect_path: Path = PROJECT_ROOT / "scripts" / "batch_recollect.py"
    db_file: Path = DEFAULT_DB_FILE
    backups_dir: Path = DEFAULT_BACKUPS_DIR
    state_dir: Path = DEFAULT_STATE_DIR
    log_dir: Path = DEFAULT_LOG_DIR
    reports_dir: Path = DEFAULT_REPORTS_DIR
    lock_file: Path = DEFAULT_LOCK_FILE
    status_file: Path = DEFAULT_STATUS_FILE
    lock_stale_minutes: float = DEFAULT_LOCK_STALE_MINUTES
    market_schedule: bool = False


@dataclass(frozen=True)
class ScheduleDecision:
    active: bool
    interval_seconds: int
    label: str


def is_placeholder_url(url: str) -> bool:
    return any(pattern in url for pattern in PLACEHOLDER_PATTERNS)


def list_url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def list_url_preview(url: str, *, keep: int = 32) -> str:
    return url[:keep] + "..."


def calculate_max_runs(duration_hours: float, interval_seconds: int) -> int:
    if duration_hours <= 0:
        raise ValueError("--duration-hours must be positive")
    if interval_seconds <= 0:
        raise ValueError("--interval-seconds must be positive")
    return max(1, math.ceil(duration_hours * 3600 / interval_seconds))


def seconds_until_next_local_time(now: datetime, target: datetime_time) -> int:
    target_dt = now.replace(
        hour=target.hour,
        minute=target.minute,
        second=target.second,
        microsecond=0,
    )
    if target_dt <= now:
        target_dt += timedelta(days=1)
    return max(1, int((target_dt - now).total_seconds()))


def market_schedule_decision(now: datetime) -> ScheduleDecision:
    current = now.time()
    if current >= datetime_time(23, 0) or current < datetime_time(6, 0):
        return ScheduleDecision(
            active=False,
            interval_seconds=seconds_until_next_local_time(now, datetime_time(6, 0)),
            label="market-closed-23-06",
        )
    if current < datetime_time(7, 0):
        return ScheduleDecision(active=True, interval_seconds=1800, label="market-06-07-30m")
    if current < datetime_time(8, 0):
        return ScheduleDecision(active=True, interval_seconds=600, label="market-07-08-10m")
    if current < datetime_time(16, 0):
        return ScheduleDecision(active=True, interval_seconds=300, label="market-08-16-5m")
    if current < datetime_time(18, 0):
        return ScheduleDecision(active=True, interval_seconds=600, label="market-16-18-10m")
    return ScheduleDecision(active=True, interval_seconds=1800, label="market-18-23-30m")


def schedule_decision_for(
    config: LoopConfig,
    now: datetime,
) -> ScheduleDecision:
    if config.market_schedule:
        return market_schedule_decision(now)
    return ScheduleDecision(active=True, interval_seconds=config.interval_seconds, label="fixed-interval")


def build_archive_cycle_commands(config: LoopConfig) -> list[list[str]]:
    return [
        build_index_tail_command(config),
        build_batch_recollect_command(config),
    ]


def build_index_tail_command(config: LoopConfig) -> list[str]:
    index_script = "index_tail_realtime.py" if config.realtime_index else "index_tail.py"
    command = [
        config.python,
        str(PROJECT_ROOT / "scripts" / index_script),
        config.list_url,
        "--collect-after-snapshot",
    ]
    if config.interactive_login:
        command.append("--interactive-login")
    if config.realtime_index:
        command.extend(["--stop-after-empty-pages", str(config.stop_after_empty_pages)])
    return command


def build_batch_recollect_command(config: LoopConfig) -> list[str]:
    return [
        config.python,
        str(PROJECT_ROOT / "scripts" / "batch_recollect.py"),
    ]


def is_index_tail_command(command: list[str]) -> bool:
    return len(command) >= 2 and Path(command[1]).name in {"index_tail.py", "index_tail_realtime.py"}


def build_daily_archive_command(config: LoopConfig) -> list[str]:
    """Compatibility wrapper; the loop now uses the proven index_tail path."""
    return build_index_tail_command(config)


def summarize(text: str, *, max_chars: int = 1200) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."


def contains_block_signal(stdout: str, stderr: str) -> str | None:
    combined = f"{stdout}\n{stderr}"
    for line in combined.splitlines():
        for label, pattern in BLOCK_SIGNAL_PATTERNS:
            if pattern.search(line):
                return label
    return None


def index_tail_completed(stdout: str) -> bool:
    return "[index_tail]" in stdout and ("complete" in stdout.lower() or "완료" in stdout)


def parse_failed_count(stdout: str) -> int | None:
    match = re.search(r"^\s*failed\s*:\s*(\d+)\s*$", stdout, flags=re.MULTILINE)
    if not match:
        return None
    return int(match.group(1))


def parse_summary_value(stdout: str, name: str) -> int | None:
    match = re.search(rf"^\s*{re.escape(name)}\s*:\s*(\d+)\s*$", stdout, flags=re.MULTILINE)
    if not match:
        return None
    return int(match.group(1))


def parse_report_path(stdout: str) -> str | None:
    match = re.search(r"^\s*report\s*:\s*(.+?)\s*$", stdout, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1)


def archive_cycle_reached_recollect(result: RunResult) -> bool:
    return "batch_recollect.py" in result.stdout


def log_path_for(log_dir: Path, started_at: datetime) -> Path:
    return log_dir / f"{started_at.date().isoformat()}.log"


def append_log(config: LoopConfig, result: RunResult, stop_reason: str | None = None) -> Path:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    path = log_path_for(config.log_dir, result.started_at)
    lines = [
        "===",
        f"run_number: {result.run_number}",
        f"started_at: {result.started_at.isoformat()}",
        f"finished_at: {result.finished_at.isoformat()}",
        f"returncode: {result.returncode}",
        "commands:",
        *("  " + " ".join(command) for command in result.commands),
        f"archive_db_before_count: {display_status_value(result.before_article_count)}",
        f"archive_db_after_count: {display_status_value(result.after_article_count)}",
        f"latest_article_id: {display_status_value(result.latest_article_id)}",
        f"stdout_summary: {summarize(result.stdout)}",
        f"stderr_summary: {summarize(result.stderr)}",
    ]
    if stop_reason:
        lines.append(f"stop_reason: {stop_reason}")
    lines.extend(["stdout:", result.stdout.rstrip(), "stderr:", result.stderr.rstrip(), ""])
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
        fh.write("\n")
    return path


def append_schedule_skip_log(
    config: LoopConfig,
    loop_number: int,
    checked_at: datetime,
    decision: ScheduleDecision,
) -> Path:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    path = log_path_for(config.log_dir, checked_at)
    lines = [
        "===",
        f"run_number: {loop_number}",
        f"checked_at: {checked_at.isoformat()}",
        "skipped: market schedule inactive",
        f"schedule_label: {decision.label}",
        f"next_interval_seconds: {decision.interval_seconds}",
        "",
    ]
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
        fh.write("\n")
    return path


def base_status(config: LoopConfig, started_at: datetime, max_runs: int) -> dict[str, object]:
    return {
        "started_at": started_at.isoformat(),
        "updated_at": started_at.isoformat(),
        "current_run": 0,
        "max_runs": max_runs,
        "interval_seconds": config.interval_seconds,
        "schedule_mode": "market" if config.market_schedule else "fixed",
        "next_interval_seconds": config.interval_seconds,
        "last_schedule_label": None,
        "last_schedule_active": None,
        "last_schedule_skipped_at": None,
        "duration_hours": config.duration_hours,
        "limit": config.limit,
        "list_url_hash": list_url_hash(config.list_url),
        "list_url_preview": list_url_preview(config.list_url),
        "last_run_started_at": None,
        "last_run_finished_at": None,
        "last_return_code": None,
        "last_saved": None,
        "last_duplicates": None,
        "last_failed": None,
        "last_latest_article_id": None,
        "last_run_warning": None,
        "last_report_path": None,
        "stop_reason": None,
        "is_running": True,
    }


def write_status(config: LoopConfig, status: dict[str, object]) -> None:
    config.status_file.parent.mkdir(parents=True, exist_ok=True)
    status["updated_at"] = datetime.now().isoformat()
    config.status_file.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    touch_lock(config)


def lock_payload(config: LoopConfig, started_at: datetime) -> dict[str, object]:
    now = datetime.now().isoformat()
    return {
        "pid": os.getpid(),
        "started_at": started_at.isoformat(),
        "updated_at": now,
        "command": config.argv_summary or " ".join(sys.argv),
        "lock_version": LOCK_VERSION,
    }


def write_lock(config: LoopConfig, payload: dict[str, object]) -> None:
    config.lock_file.parent.mkdir(parents=True, exist_ok=True)
    config.lock_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def create_lock_exclusive(config: LoopConfig, payload: dict[str, object]) -> bool:
    config.lock_file.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(config.lock_file, flags)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return True


def touch_lock(config: LoopConfig) -> None:
    if not config.lock_file.exists():
        return
    try:
        data = json.loads(config.lock_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if data.get("pid") != os.getpid():
        return
    data["updated_at"] = datetime.now().isoformat()
    write_lock(config, data)


def lock_is_stale_or_corrupt(config: LoopConfig) -> tuple[bool, str]:
    try:
        data = json.loads(config.lock_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return True, f"corrupt lock file ({exc.__class__.__name__})"

    required_fields = ("pid", "started_at", "updated_at", "command", "lock_version")
    missing = [field for field in required_fields if field not in data]
    if missing:
        return True, "corrupt lock file (missing " + ", ".join(missing) + ")"

    try:
        updated_at = datetime.fromisoformat(str(data["updated_at"]))
    except ValueError:
        return True, "corrupt lock file (invalid updated_at)"

    stale_after = timedelta(minutes=config.lock_stale_minutes)
    now = datetime.now(updated_at.tzinfo) if updated_at.tzinfo else datetime.now()
    if now - updated_at > stale_after:
        return True, f"stale lock file (updated_at={data['updated_at']})"
    return False, f"pid={data['pid']}, updated_at={data['updated_at']}"


def acquire_lock(config: LoopConfig, started_at: datetime) -> bool:
    payload = lock_payload(config, started_at)
    if create_lock_exclusive(config, payload):
        return True

    if config.lock_file.exists():
        can_takeover, reason = lock_is_stale_or_corrupt(config)
        if not can_takeover:
            print(f"[archive_loop] ERROR: another archive loop appears to be running ({reason}).")
            print(f"[archive_loop] lock file: {config.lock_file}")
            return False
        print(f"[archive_loop] taking over {reason}: {config.lock_file}")
        try:
            config.lock_file.unlink()
        except FileNotFoundError:
            pass
        if create_lock_exclusive(config, payload):
            return True

    print(f"[archive_loop] ERROR: could not acquire lock file: {config.lock_file}")
    return False


def release_lock(config: LoopConfig) -> None:
    if not config.lock_file.exists():
        return
    try:
        data = json.loads(config.lock_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if data.get("pid") != os.getpid():
        return
    try:
        config.lock_file.unlink()
    except FileNotFoundError:
        return


def update_status_for_run_start(
    config: LoopConfig,
    status: dict[str, object],
    run_number: int,
    started_at: datetime,
) -> None:
    status["current_run"] = run_number
    status["last_run_started_at"] = started_at.isoformat()
    status["last_run_finished_at"] = None
    status["last_return_code"] = None
    status["is_running"] = True
    write_status(config, status)


def update_status_for_schedule_decision(
    config: LoopConfig,
    status: dict[str, object],
    loop_number: int,
    decision: ScheduleDecision,
    checked_at: datetime,
) -> None:
    status["current_run"] = loop_number
    status["schedule_mode"] = "market" if config.market_schedule else "fixed"
    status["next_interval_seconds"] = decision.interval_seconds
    status["last_schedule_label"] = decision.label
    status["last_schedule_active"] = decision.active
    if not decision.active:
        status["last_schedule_skipped_at"] = checked_at.isoformat()
    status["is_running"] = True
    write_status(config, status)


def update_status_for_run_finish(
    config: LoopConfig,
    status: dict[str, object],
    result: RunResult,
    stop_reason: str | None,
) -> None:
    status["last_run_started_at"] = result.started_at.isoformat()
    status["last_run_finished_at"] = result.finished_at.isoformat()
    status["last_return_code"] = result.returncode
    saved = parse_summary_value(result.stdout, "saved")
    if saved is None and result.before_article_count is not None and result.after_article_count is not None:
        saved = max(0, result.after_article_count - result.before_article_count)
    status["last_saved"] = saved
    status["last_duplicates"] = parse_summary_value(result.stdout, "duplicates")
    status["last_failed"] = parse_summary_value(result.stdout, "failed")
    if status["last_failed"] is None and result.returncode != 0:
        status["last_failed"] = 1
    status["last_latest_article_id"] = result.latest_article_id
    status["last_run_warning"] = stop_reason
    status["last_report_path"] = parse_report_path(result.stdout)
    write_status(config, status)


def finalize_status(config: LoopConfig, status: dict[str, object], stop_reason: str) -> None:
    status["is_running"] = False
    status["stop_reason"] = stop_reason
    write_status(config, status)


def format_status_summary(data: dict[str, object]) -> str:
    fields = [
        ("running", "is_running"),
        ("started_at", "started_at"),
        ("updated_at", "updated_at"),
        ("current_run / max_runs", None),
        ("interval_seconds", "interval_seconds"),
        ("schedule_mode", "schedule_mode"),
        ("next_interval_seconds", "next_interval_seconds"),
        ("last_schedule_label", "last_schedule_label"),
        ("last_schedule_active", "last_schedule_active"),
        ("last_schedule_skipped_at", "last_schedule_skipped_at"),
        ("duration_hours", "duration_hours"),
        ("limit", "limit"),
        ("list_url_preview", "list_url_preview"),
        ("last_run_started_at", "last_run_started_at"),
        ("last_run_finished_at", "last_run_finished_at"),
        ("last_return_code", "last_return_code"),
        ("last_saved", "last_saved"),
        ("last_duplicates", "last_duplicates"),
        ("last_failed", "last_failed"),
        ("last_latest_article_id", "last_latest_article_id"),
        ("last_run_warning", "last_run_warning"),
        ("last_report_path", "last_report_path"),
        ("stop_reason", "stop_reason"),
    ]
    lines = ["[archive_loop] status"]
    for label, key in fields:
        if key is None:
            current_run = data.get("current_run")
            max_runs = data.get("max_runs")
            value = f"{display_status_value(current_run)} / {display_status_value(max_runs)}"
        else:
            value = display_status_value(data.get(key))
        lines.append(f"  {label}: {value}")
    return "\n".join(lines)


def display_status_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def print_status(path: Path) -> int:
    if not path.exists():
        print(f"[archive_loop] no status file: {path}")
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    print(format_status_summary(data))
    return 0


def readonly_article_count(db_file: Path) -> int:
    uri = f"file:{db_file.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
    return int(row[0])


def readonly_archive_summary(db_file: Path = DEFAULT_DB_FILE) -> dict[str, int | None]:
    summary: dict[str, int | None] = {
        "article_count": None,
        "latest_article_id": None,
    }
    if not db_file.exists():
        return summary
    uri = f"file:{db_file.resolve().as_posix()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as conn:
            summary["article_count"] = int(conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0])
            columns = {row[1] for row in conn.execute("PRAGMA table_info(articles)").fetchall()}
            if "article_id" in columns:
                row = conn.execute("SELECT MAX(article_id) FROM articles").fetchone()
                summary["latest_article_id"] = int(row[0]) if row and row[0] is not None else None
    except sqlite3.Error:
        return summary
    return summary


def check_creatable_dir(path: Path) -> tuple[str, str]:
    if path.exists():
        if path.is_dir():
            return "OK", f"{path} exists"
        return "FAIL", f"{path} exists but is not a directory"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return "FAIL", f"{path} cannot be created ({exc})"
    return "OK", f"{path} created"


def status_summary_for_preflight(path: Path) -> tuple[str, str]:
    if not path.exists():
        return "WARN", f"status file not found: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return "WARN", f"status file cannot be read ({exc.__class__.__name__}): {path}"
    running = display_status_value(data.get("is_running"))
    updated_at = display_status_value(data.get("updated_at"))
    stop_reason = display_status_value(data.get("stop_reason"))
    return "OK", f"running={running}, updated_at={updated_at}, stop_reason={stop_reason}"


def lock_summary_for_preflight(config: PreflightConfig) -> tuple[str, str]:
    if not config.lock_file.exists():
        return "OK", f"lock file not found: {config.lock_file}"
    lock_config = LoopConfig(
        list_url="preflight",
        lock_file=config.lock_file,
        lock_stale_minutes=config.lock_stale_minutes,
    )
    can_takeover, reason = lock_is_stale_or_corrupt(lock_config)
    if can_takeover:
        return "WARN", f"{reason}: {config.lock_file}"
    return "WARN", f"current lock present ({reason}): {config.lock_file}"


def print_preflight_result(level: str, label: str, detail: str) -> str:
    print(f"[{level}] {label}: {detail}")
    return level


def run_preflight(config: PreflightConfig | None = None) -> int:
    config = config or PreflightConfig()
    levels: list[str] = []
    print("[archive_loop] preflight")
    print("[archive_loop] no collection, browser, network, or execute mode is run")

    cwd = Path.cwd().resolve()
    project_root = config.project_root.resolve()
    if cwd == project_root:
        levels.append(print_preflight_result("OK", "working directory", str(cwd)))
    else:
        levels.append(print_preflight_result("WARN", "working directory", f"{cwd} (expected {project_root})"))

    if config.index_tail_path.exists():
        levels.append(print_preflight_result("OK", "index_tail.py", str(config.index_tail_path)))
    else:
        levels.append(print_preflight_result("FAIL", "index_tail.py", f"missing: {config.index_tail_path}"))

    if config.batch_recollect_path.exists():
        levels.append(print_preflight_result("OK", "batch_recollect.py", str(config.batch_recollect_path)))
    else:
        levels.append(print_preflight_result("FAIL", "batch_recollect.py", f"missing: {config.batch_recollect_path}"))

    if not config.db_file.exists():
        levels.append(print_preflight_result("FAIL", "archive.db", f"missing: {config.db_file}"))
    else:
        try:
            article_count = readonly_article_count(config.db_file)
        except sqlite3.Error as exc:
            levels.append(print_preflight_result("FAIL", "archive.db", f"read-only count failed ({exc})"))
        else:
            if article_count == 0:
                levels.append(print_preflight_result("FAIL", "archive.db articles", "count=0"))
            else:
                levels.append(print_preflight_result("OK", "archive.db articles", f"count={article_count}"))

    if config.backups_dir.is_dir():
        levels.append(print_preflight_result("OK", "backups directory", str(config.backups_dir)))
    else:
        levels.append(print_preflight_result("FAIL", "backups directory", f"missing: {config.backups_dir}"))

    for label, path in (
        ("state directory", config.state_dir),
        ("loop log directory", config.log_dir),
        ("reports directory", config.reports_dir),
    ):
        level, detail = check_creatable_dir(path)
        levels.append(print_preflight_result(level, label, detail))

    level, detail = lock_summary_for_preflight(config)
    levels.append(print_preflight_result(level, "archive_loop.lock", detail))

    level, detail = status_summary_for_preflight(config.status_file)
    levels.append(print_preflight_result(level, "archive_loop_status.json", detail))

    print("[OK] proven collection path: index_tail.py --collect-after-snapshot, then batch_recollect.py")
    print("[WARN] browser/session mode: this loop preserves the existing script behavior; it does not add login or marker logic")
    levels.extend(["OK", "WARN"])

    schedule_mode = "market" if config.market_schedule else "fixed"
    print(f"[OK] schedule mode: {schedule_mode}")
    if config.market_schedule:
        print("[OK] market schedule: 23:00-06:00 stop, 06:00-07:00 30m, 07:00-08:00 10m, 08:00-16:00 5m, 16:00-18:00 10m, 18:00-23:00 30m")
        levels.append("OK")
    levels.append("OK")

    print("[OK] list-url: not required for preflight")
    print("[WARN] list-url: real collection still requires the mentor teacher article-list URL")
    levels.extend(["OK", "WARN"])

    fail_count = levels.count("FAIL")
    warn_count = levels.count("WARN")
    ok_count = levels.count("OK")
    print(f"[archive_loop] summary: ok={ok_count}, warn={warn_count}, fail={fail_count}")
    return 2 if fail_count else 0


class _TeeTextIO:
    def __init__(self, capture: io.StringIO, stream) -> None:
        self.capture = capture
        self.stream = stream

    def write(self, text: str) -> int:
        self.capture.write(text)
        written = self.stream.write(text)
        self.stream.flush()
        return written

    def flush(self) -> None:
        self.capture.flush()
        self.stream.flush()


def _emit_realtime_stdout(stdout_parts: list[str], line: str) -> None:
    print(line, flush=True)
    stdout_parts.append(line)


def _capture_function_call(func: Callable[..., int], *args, **kwargs) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    returncode = 0
    tee_stdout = _TeeTextIO(stdout, sys.stdout)
    tee_stderr = _TeeTextIO(stderr, sys.stderr)
    with contextlib.redirect_stdout(tee_stdout), contextlib.redirect_stderr(tee_stderr):
        try:
            returncode = int(func(*args, **kwargs))
        except SystemExit as exc:
            if isinstance(exc.code, int):
                returncode = exc.code
            elif exc.code is None:
                returncode = 0
            else:
                print(exc.code, file=sys.stderr)
                returncode = 1
        except Exception:
            traceback.print_exc(file=sys.stderr)
            returncode = 1
    return returncode, stdout.getvalue(), stderr.getvalue()


def run_once_realtime_session(
    config: LoopConfig,
    run_number: int,
    *,
    browser_session_factory: Callable[[], object] | None = None,
    realtime_index_runner: Callable[..., int] | None = None,
    batch_recollect_runner: Callable[..., int] | None = None,
) -> RunResult:
    commands = build_archive_cycle_commands(config)
    before_summary = readonly_archive_summary(config.db_file)
    started_at = datetime.now()
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    returncode = 0

    if browser_session_factory is None:
        from browser import BrowserSession

        browser_session_factory = BrowserSession
    if realtime_index_runner is None:
        from index_tail_realtime import run_realtime_index

        realtime_index_runner = run_realtime_index
    if batch_recollect_runner is None:
        from batch_recollect import run_batch_recollect

        batch_recollect_runner = run_batch_recollect

    session = browser_session_factory()
    try:
        index_command = commands[0]
        _emit_realtime_stdout(
            stdout_parts,
            "[archive_loop] step 1/2: realtime title collection started",
        )
        index_returncode, command_stdout, command_stderr = _capture_function_call(
            realtime_index_runner,
            config.list_url,
            session,
            interactive_login=config.interactive_login,
            stop_after_empty_pages=config.stop_after_empty_pages,
        )
        stdout_parts.append("$ " + " ".join(index_command))
        if command_stdout:
            stdout_parts.append(command_stdout)
        if command_stderr:
            stderr_parts.append("$ " + " ".join(index_command))
            stderr_parts.append(command_stderr)
        after_index_summary = readonly_archive_summary(config.db_file)
        title_saved_delta = None
        if before_summary["article_count"] is not None and after_index_summary["article_count"] is not None:
            title_saved_delta = max(0, after_index_summary["article_count"] - before_summary["article_count"])
        _emit_realtime_stdout(
            stdout_parts,
            "[archive_loop] title collection finished: "
            f"saved_delta={display_status_value(title_saved_delta)} "
            f"latest_id={display_status_value(after_index_summary['latest_article_id'])}",
        )
        if index_returncode != 0:
            returncode = index_returncode
        elif contains_block_signal(command_stdout, command_stderr) and not index_tail_completed(command_stdout):
            returncode = 0
        else:
            batch_command = commands[1]
            _emit_realtime_stdout(
                stdout_parts,
                "[archive_loop] step 2/2: body collection started",
            )
            batch_returncode, command_stdout, command_stderr = _capture_function_call(
                batch_recollect_runner,
                session=session,
            )
            stdout_parts.append("$ " + " ".join(batch_command))
            if command_stdout:
                stdout_parts.append(command_stdout)
            if command_stderr:
                stderr_parts.append("$ " + " ".join(batch_command))
                stderr_parts.append(command_stderr)
            if batch_returncode != 0:
                returncode = batch_returncode
            _emit_realtime_stdout(
                stdout_parts,
                "[archive_loop] body collection finished",
            )
    finally:
        try:
            session.close()
        except Exception:
            pass

    after_summary = readonly_archive_summary(config.db_file)
    finished_at = datetime.now()
    cycle_saved_delta = None
    if before_summary["article_count"] is not None and after_summary["article_count"] is not None:
        cycle_saved_delta = max(0, after_summary["article_count"] - before_summary["article_count"])
    _emit_realtime_stdout(
        stdout_parts,
        f"[archive_loop] cycle {run_number} finished: "
        f"returncode={returncode} "
        f"saved_delta={display_status_value(cycle_saved_delta)} "
        f"latest_id={display_status_value(after_summary['latest_article_id'])}",
    )
    return RunResult(
        run_number=run_number,
        started_at=started_at,
        finished_at=finished_at,
        returncode=returncode,
        stdout="\n".join(stdout_parts),
        stderr="\n".join(stderr_parts),
        commands=commands,
        before_article_count=before_summary["article_count"],
        after_article_count=after_summary["article_count"],
        latest_article_id=after_summary["latest_article_id"],
    )


def run_once(
    config: LoopConfig,
    run_number: int,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> RunResult:
    if config.realtime_index:
        return run_once_realtime_session(config, run_number)

    commands = build_archive_cycle_commands(config)
    before_summary = readonly_archive_summary(config.db_file)
    started_at = datetime.now()
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    returncode = 0
    for command in commands:
        completed = runner(command, text=True, capture_output=True, check=False)
        command_stdout = completed.stdout or ""
        command_stderr = completed.stderr or ""
        stdout_parts.append("$ " + " ".join(command))
        if command_stdout:
            stdout_parts.append(command_stdout)
        if command_stderr:
            stderr_parts.append("$ " + " ".join(command))
            stderr_parts.append(command_stderr)
        if completed.returncode != 0:
            returncode = completed.returncode
            break
        if (
            is_index_tail_command(command)
            and contains_block_signal(command_stdout, command_stderr)
            and not index_tail_completed(command_stdout)
        ):
            break
    after_summary = readonly_archive_summary(config.db_file)
    finished_at = datetime.now()
    return RunResult(
        run_number=run_number,
        started_at=started_at,
        finished_at=finished_at,
        returncode=returncode,
        stdout="\n".join(stdout_parts),
        stderr="\n".join(stderr_parts),
        commands=commands,
        before_article_count=before_summary["article_count"],
        after_article_count=after_summary["article_count"],
        latest_article_id=after_summary["latest_article_id"],
    )


def print_run_summary(result: RunResult, log_path: Path) -> None:
    print(f"[archive_loop] run_number : {result.run_number}")
    print(f"[archive_loop] started_at : {result.started_at.isoformat()}")
    print(f"[archive_loop] finished_at: {result.finished_at.isoformat()}")
    print(f"[archive_loop] returncode : {result.returncode}")
    if result.before_article_count is not None and result.after_article_count is not None:
        print(f"[archive_loop] saved_delta: {max(0, result.after_article_count - result.before_article_count)}")
    print(f"[archive_loop] latest_id : {display_status_value(result.latest_article_id)}")
    print(f"[archive_loop] stdout    : {summarize(result.stdout)}")
    print(f"[archive_loop] stderr    : {summarize(result.stderr)}")
    print(f"[archive_loop] log       : {log_path}")


def run_loop(
    config: LoopConfig,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = datetime.now,
) -> int:
    if is_placeholder_url(config.list_url):
        print("[archive_loop] ERROR: --list-url looks like a placeholder; refusing to run.")
        return 2
    if config.limit < 1:
        print("[archive_loop] ERROR: --limit must be positive.")
        return 2

    max_runs = config.max_runs or calculate_max_runs(
        config.duration_hours,
        config.interval_seconds,
    )
    loop_started_at = clock()
    if not acquire_lock(config, loop_started_at):
        return 3

    status = base_status(config, loop_started_at, max_runs)
    stop_at = loop_started_at + timedelta(hours=config.duration_hours)

    try:
        write_status(config, status)
        for run_number in range(1, max_runs + 1):
            now = clock()
            if now >= stop_at:
                print("[archive_loop] duration reached before next run.")
                finalize_status(config, status, "duration reached before next run")
                return 0

            decision = schedule_decision_for(config, now)
            update_status_for_schedule_decision(config, status, run_number, decision, now)
            if not decision.active:
                path = append_schedule_skip_log(config, run_number, now, decision)
                print(f"[archive_loop] market schedule inactive: {decision.label}")
                print(f"[archive_loop] next_interval_seconds: {decision.interval_seconds}")
                print(f"[archive_loop] log       : {path}")
                if run_number < max_runs:
                    sleeper(decision.interval_seconds)
                continue

            run_started_at = clock()
            update_status_for_run_start(config, status, run_number, run_started_at)
            result = run_once(config, run_number, runner=runner)
            stop_reason = stop_reason_for(config, result)
            update_status_for_run_finish(config, status, result, stop_reason)
            path = append_log(config, result, stop_reason=stop_reason)
            print_run_summary(result, path)

            if stop_reason:
                print(f"[archive_loop] stopping: {stop_reason}")
                finalize_status(config, status, stop_reason)
                return 1 if result.returncode != 0 else 0

            if run_number < max_runs:
                sleeper(decision.interval_seconds)

        finalize_status(config, status, "max runs completed")
        return 0
    except KeyboardInterrupt:
        finalize_status(config, status, "keyboard interrupt")
        print("[archive_loop] stopping: keyboard interrupt")
        return 130
    finally:
        release_lock(config)


def stop_reason_for(config: LoopConfig, result: RunResult) -> str | None:
    if result.returncode != 0:
        return f"archive cycle returned non-zero exit code {result.returncode}"
    if not archive_cycle_reached_recollect(result):
        block_signal = contains_block_signal(result.stdout, result.stderr)
        if block_signal:
            return f"block signal detected: {block_signal}"
    failed_count = parse_failed_count(result.stdout)
    if failed_count is not None and failed_count > 0 and failed_count >= config.stop_on_failed:
        return f"failed count {failed_count} exceeded threshold {config.stop_on_failed}"
    return None


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repeat the proven index_tail.py and batch_recollect.py archive path on a bounded interval.",
    )
    parser.add_argument("--list-url", help="Naver Cafe list URL")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="retained for status compatibility; dedupe is handled by archive.db")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--duration-hours", type=float, default=DEFAULT_DURATION_HOURS)
    parser.add_argument("--max-runs", type=int, default=None)
    parser.add_argument("--stop-on-failed", type=int, default=0)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--status-file", type=Path, default=DEFAULT_STATUS_FILE)
    parser.add_argument(
        "--interactive-login",
        action="store_true",
        help="pass --interactive-login to index_tail.py for the existing manual login flow",
    )
    parser.add_argument(
        "--realtime-index",
        action="store_true",
        help="use index_tail_realtime.py for the title indexing step",
    )
    parser.add_argument(
        "--stop-after-empty-pages",
        type=int,
        default=5,
        help="with --realtime-index, stop title indexing after N consecutive pages save 0 articles",
    )
    parser.add_argument(
        "--market-schedule",
        action="store_true",
        help="use local time windows: 23:00-06:00 stop, 06:00-07:00 30m, 07:00-08:00 10m, 08:00-16:00 5m, 16:00-18:00 10m, 18:00-23:00 30m",
    )
    parser.add_argument("--status", action="store_true", help="print loop status and exit")
    parser.add_argument("--preflight", action="store_true", help="run read-only operational safety checks and exit")
    parser.add_argument(
        "--lock-stale-minutes",
        type=float,
        default=DEFAULT_LOCK_STALE_MINUTES,
        help="minutes before archive_loop.lock can be treated as stale",
    )
    args = parser.parse_args(argv)
    if args.status or args.preflight:
        return args
    if not args.list_url:
        parser.error("--list-url is required unless --status is used")
    if args.max_runs is not None and args.max_runs < 1:
        parser.error("--max-runs must be positive")
    if args.stop_on_failed < 0:
        parser.error("--stop-on-failed must be non-negative")
    if args.lock_stale_minutes < 0:
        parser.error("--lock-stale-minutes must be non-negative")
    if args.stop_after_empty_pages < 1:
        parser.error("--stop-after-empty-pages must be positive")
    return args


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.status:
        return print_status(args.status_file)
    if args.preflight:
        return run_preflight(
            PreflightConfig(
                log_dir=args.log_dir,
                status_file=args.status_file,
                lock_stale_minutes=args.lock_stale_minutes,
                market_schedule=args.market_schedule,
            )
        )
    config = LoopConfig(
        list_url=args.list_url,
        limit=args.limit,
        interval_seconds=args.interval_seconds,
        duration_hours=args.duration_hours,
        max_runs=args.max_runs,
        stop_on_failed=args.stop_on_failed,
        python=args.python,
        log_dir=args.log_dir,
        status_file=args.status_file,
        lock_stale_minutes=args.lock_stale_minutes,
        market_schedule=args.market_schedule,
        interactive_login=args.interactive_login,
        realtime_index=args.realtime_index,
        stop_after_empty_pages=args.stop_after_empty_pages,
        argv_summary=" ".join(argv if argv is not None else sys.argv[1:]),
    )
    return run_loop(config)


if __name__ == "__main__":
    raise SystemExit(main())
