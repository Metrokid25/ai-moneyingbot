"""Run bounded daily archive collection on a fixed interval.

This wrapper intentionally delegates each collection pass to
`scripts/daily_archive.py --execute --limit N --list-url URL`.
It does not perform collection directly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INTERVAL_SECONDS = 600
DEFAULT_DURATION_HOURS = 24.0
DEFAULT_LIMIT = 10
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs" / "archive_loop"
DEFAULT_STATUS_FILE = PROJECT_ROOT / "state" / "archive_loop_status.json"
BLOCK_PATTERNS = (
    "captcha",
    "로그인",
    "login",
    "권한",
    "permission",
    "연령",
    "차단",
    "block",
    "blocked",
    "인증",
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


@dataclass
class RunResult:
    run_number: int
    started_at: datetime
    finished_at: datetime
    returncode: int
    stdout: str
    stderr: str
    command: list[str]


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


def build_daily_archive_command(config: LoopConfig) -> list[str]:
    return [
        config.python,
        str(PROJECT_ROOT / "scripts" / "daily_archive.py"),
        "--execute",
        "--limit",
        str(config.limit),
        "--list-url",
        config.list_url,
    ]


def summarize(text: str, *, max_chars: int = 1200) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."


def contains_block_signal(stdout: str, stderr: str) -> str | None:
    combined = f"{stdout}\n{stderr}"
    combined_lower = combined.lower()
    for pattern in BLOCK_PATTERNS:
        if pattern.lower() in combined_lower:
            return pattern
    return None


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
        "command: " + " ".join(result.command),
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


def base_status(config: LoopConfig, started_at: datetime, max_runs: int) -> dict[str, object]:
    return {
        "started_at": started_at.isoformat(),
        "updated_at": started_at.isoformat(),
        "current_run": 0,
        "max_runs": max_runs,
        "interval_seconds": config.interval_seconds,
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


def update_status_for_run_finish(
    config: LoopConfig,
    status: dict[str, object],
    result: RunResult,
    stop_reason: str | None,
) -> None:
    status["last_run_started_at"] = result.started_at.isoformat()
    status["last_run_finished_at"] = result.finished_at.isoformat()
    status["last_return_code"] = result.returncode
    status["last_saved"] = parse_summary_value(result.stdout, "saved")
    status["last_duplicates"] = parse_summary_value(result.stdout, "duplicates")
    status["last_failed"] = parse_summary_value(result.stdout, "failed")
    status["last_report_path"] = parse_report_path(result.stdout)
    status["stop_reason"] = stop_reason
    write_status(config, status)


def finalize_status(config: LoopConfig, status: dict[str, object], stop_reason: str) -> None:
    status["is_running"] = False
    status["stop_reason"] = stop_reason
    write_status(config, status)


def print_status(path: Path) -> int:
    if not path.exists():
        print(f"[archive_loop] no status file: {path}")
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def run_once(
    config: LoopConfig,
    run_number: int,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> RunResult:
    command = build_daily_archive_command(config)
    started_at = datetime.now()
    completed = runner(command, text=True, capture_output=True, check=False)
    finished_at = datetime.now()
    return RunResult(
        run_number=run_number,
        started_at=started_at,
        finished_at=finished_at,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        command=command,
    )


def print_run_summary(result: RunResult, log_path: Path) -> None:
    print(f"[archive_loop] run_number : {result.run_number}")
    print(f"[archive_loop] started_at : {result.started_at.isoformat()}")
    print(f"[archive_loop] finished_at: {result.finished_at.isoformat()}")
    print(f"[archive_loop] returncode : {result.returncode}")
    print(f"[archive_loop] stdout    : {summarize(result.stdout)}")
    print(f"[archive_loop] stderr    : {summarize(result.stderr)}")
    print(f"[archive_loop] log       : {log_path}")


def run_loop(
    config: LoopConfig,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
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
    loop_started_at = datetime.now()
    status = base_status(config, loop_started_at, max_runs)
    write_status(config, status)
    stop_at = loop_started_at + timedelta(hours=config.duration_hours)

    for run_number in range(1, max_runs + 1):
        if datetime.now() >= stop_at:
            print("[archive_loop] duration reached before next run.")
            finalize_status(config, status, "duration reached before next run")
            return 0

        run_started_at = datetime.now()
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
            sleeper(config.interval_seconds)

    finalize_status(config, status, "max runs completed")
    return 0


def stop_reason_for(config: LoopConfig, result: RunResult) -> str | None:
    if result.returncode != 0:
        return f"daily_archive returned non-zero exit code {result.returncode}"
    block_signal = contains_block_signal(result.stdout, result.stderr)
    if block_signal:
        return f"block signal detected: {block_signal}"
    failed_count = parse_failed_count(result.stdout)
    if failed_count is not None and failed_count > config.stop_on_failed:
        return f"failed count {failed_count} exceeded threshold {config.stop_on_failed}"
    return None


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run daily_archive.py execute mode on a bounded interval.",
    )
    parser.add_argument("--list-url", help="Naver Cafe list URL")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--duration-hours", type=float, default=DEFAULT_DURATION_HOURS)
    parser.add_argument("--max-runs", type=int, default=None)
    parser.add_argument("--stop-on-failed", type=int, default=0)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--status-file", type=Path, default=DEFAULT_STATUS_FILE)
    parser.add_argument("--status", action="store_true", help="print loop status and exit")
    args = parser.parse_args(argv)
    if args.status:
        return args
    if not args.list_url:
        parser.error("--list-url is required unless --status is used")
    if args.max_runs is not None and args.max_runs < 1:
        parser.error("--max-runs must be positive")
    if args.stop_on_failed < 0:
        parser.error("--stop-on-failed must be non-negative")
    return args


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.status:
        return print_status(args.status_file)
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
    )
    return run_loop(config)


if __name__ == "__main__":
    raise SystemExit(main())
