"""Unattended wrapper around the RAG incremental index update.

Runs `scripts/update_rag_index_incremental.py --execute` as a subprocess,
parses its JSON summary, retries transient failures with backoff, and reports
the outcome (indexed N chunks / failure reason) to the RAG bot's Telegram
channel. Designed to be driven once a day by Windows Task Scheduler on the
mini-PC with no human present.

Boundary: RAG-owned. Reads archive.db (read-only, via the child script) and
writes only the RAG Qdrant index + manifest. Does not touch trading-bot data.
Login/collection is the Archive bot's concern and is NOT handled here.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Load the project's .env explicitly (not via an import side effect) so the
# child subprocess inherits VOYAGE_API_KEY and RAG_TELEGRAM_* from os.environ
# regardless of the scheduler's working directory or import ordering. The child
# indexer does not load .env itself.
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except Exception:  # noqa: BLE001 - dotenv is optional; env may come from the OS
    pass

from notify_telegram import send_telegram  # noqa: E402

KST = timezone(timedelta(hours=9))
INDEXER = SCRIPTS_DIR / "update_rag_index_incremental.py"
# Same default the child indexer uses, so the liveness probe looks at the same DB.
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "archive.db"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 30.0


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def now_kst_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")


# Keys the indexer always puts in its summary; used to tell the real summary
# apart from stray JSON-looking library/telemetry output on stdout.
_SUMMARY_KEYS = ("new_chunks", "current_chunks", "collection")


def parse_summary(stdout: str) -> dict | None:
    """Extract the JSON summary object the indexer prints on stdout.

    Scan every '{', try to decode a JSON object starting there, and keep the
    last one that parses AND carries a known summary key. Anchoring on a
    signature key (not just "the first/last object") tolerates stray log lines
    printed either BEFORE or AFTER the summary — including bare '{}' teardown
    noise from imported libraries.
    """
    decoder = json.JSONDecoder()
    found: dict | None = None
    for i, ch in enumerate(stdout):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(stdout[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and any(k in obj for k in _SUMMARY_KEYS):
            found = obj
    return found


def get_last_collected(db_path: Path) -> str | None:
    """Posted date of the most recently collected article in archive.db (read-only).

    Collection-liveness signal (PM 2026-07-05): lets the operator tell "truly no
    new articles" apart from "the Archive bot's collection silently died" from
    the notification text alone. Never raises — an unattended notify run must
    not fail because the probe did; returns None and the message says 확인불가.
    """
    try:
        # Percent-escape the path: SQLite's URI parser decodes %HH and truncates
        # at '#'/'?', so a raw path containing those would open the wrong file.
        quoted = urllib.parse.quote(db_path.as_posix(), safe="/:")
        conn = sqlite3.connect(f"file:{quoted}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT posted_at, saved_at FROM articles "
                "WHERE status = 'BODY_COLLECTED' ORDER BY saved_at DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - probe must never break the notify path
        print(f"[run_rag_incremental_notify] WARN: liveness probe failed: {exc}")
        return None
    if row is None:
        return None
    posted_at, saved_at = row
    return str(posted_at or saved_at or "").strip() or None


def build_success_message(
    summary: dict, *, timestamp: str, last_collected: str | None = None
) -> str:
    new_chunks = summary.get("new_chunks", 0)
    if new_chunks:
        head = f"✅ RAG indexing 완료 · 신규 {new_chunks}청크 추가"
    else:
        head = "✅ RAG indexing · 신규 0건 (최신 상태)"
    lines = [
        head,
        f"현재 청크: {summary.get('current_chunks', '?')} / 반영됨: {summary.get('indexed_chunks', '?')}",
        f"컬렉션: {summary.get('collection', '?')}",
        # Collection-liveness: if this date stops advancing while "신규 0건"
        # repeats, the Archive bot's collection is likely down (not "no news").
        f"마지막 수집글 작성일: {last_collected or '확인불가'}",
        timestamp,
    ]
    return "\n".join(lines)


def build_failure_message(*, attempts: int, detail: str, timestamp: str) -> str:
    detail = (detail or "").strip()
    if len(detail) > 800:
        detail = detail[-800:]
    return "\n".join(
        [
            f"\U0001f534 RAG indexing 실패 (재시도 {attempts}회 소진)",
            f"사유: {detail or 'unknown error'}",
            timestamp,
        ]
    )


def run_indexer_once(
    *,
    python_exe: str,
    db_path: Path | None,
    qdrant_path: Path | None,
    collection: str | None,
    dry_run: bool,
) -> subprocess.CompletedProcess:
    cmd = [python_exe, str(INDEXER), "--dry-run" if dry_run else "--execute"]
    if db_path is not None:
        cmd += ["--db-path", str(db_path)]
    if qdrant_path is not None:
        cmd += ["--qdrant-path", str(qdrant_path)]
    if collection:
        cmd += ["--collection", collection]
    # errors="replace": a non-UTF-8 byte from the child (native lib output, a
    # cp949 traceback on Windows) must never raise UnicodeDecodeError and crash
    # the unattended run before we can report failure.
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the RAG incremental index update unattended and notify via Telegram.",
    )
    parser.add_argument("--python", default=sys.executable, help="Python interpreter for the child indexer")
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--qdrant-path", type=Path, default=None)
    parser.add_argument("--collection", default=None)
    parser.add_argument("--dry-run", action="store_true", help="pass-through: detect new chunks only")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--backoff-seconds", type=float, default=DEFAULT_BACKOFF_SECONDS)
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="run without sending Telegram (still prints summary/exit code)",
    )
    return parser.parse_args(argv)


def notify(text: str, *, enabled: bool) -> None:
    print(text)
    if not enabled:
        return
    # send_telegram already skips (with a warning) when unconfigured and never
    # raises. Surface a delivery failure loudly so a silent-alert day is visible
    # in the scheduler's captured output.
    if not send_telegram(text):
        print("[run_rag_incremental_notify] WARN: Telegram notification was NOT delivered.")


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    telegram_enabled = not args.no_telegram
    max_attempts = max(1, args.max_attempts)

    last_detail = ""
    attempts_used = 0
    for attempt in range(1, max_attempts + 1):
        attempts_used = attempt
        try:
            proc = run_indexer_once(
                python_exe=args.python,
                db_path=args.db_path,
                qdrant_path=args.qdrant_path,
                collection=args.collection,
                dry_run=args.dry_run,
            )
        except Exception as exc:  # noqa: BLE001 - never let the unattended run die uncaught
            last_detail = f"failed to launch indexer: {exc}"
            print(f"[run_rag_incremental_notify] attempt {attempt}/{max_attempts}: {last_detail}")
            if attempt < max_attempts:
                time.sleep(args.backoff_seconds)
            continue

        if proc.returncode == 0:
            summary = parse_summary(proc.stdout) or {}
            last_collected = get_last_collected(args.db_path or DEFAULT_DB_PATH)
            notify(
                build_success_message(
                    summary, timestamp=now_kst_str(), last_collected=last_collected
                ),
                enabled=telegram_enabled,
            )
            return 0

        last_detail = (proc.stderr or "") + (proc.stdout or "")
        print(f"[run_rag_incremental_notify] attempt {attempt}/{max_attempts} failed (rc={proc.returncode})")
        # rc=2 is the child's argparse usage error (bad/mutually-exclusive flags):
        # deterministic and permanent, so retrying only wastes backoff. Report now.
        if proc.returncode == 2:
            break
        if attempt < max_attempts:
            time.sleep(args.backoff_seconds)

    notify(
        build_failure_message(attempts=attempts_used, detail=last_detail, timestamp=now_kst_str()),
        enabled=telegram_enabled,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
