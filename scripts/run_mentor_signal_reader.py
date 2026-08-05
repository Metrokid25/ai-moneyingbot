"""CLI for the independent Mentor Signal Reader."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"
SCRIPTS = PROJECT_ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

from mentor_signal_reader import (  # noqa: E402
    ArchiveSource, MentorSignalReader, RuleParser, StateStore, StockMasterSnapshot,
)
from notify_telegram import send_telegram, telegram_configured  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default=os.getenv("MENTOR_SIGNAL_MODE", "shadow"),
                        choices=("shadow", "paper", "live"))
    run = parser.add_mutually_exclusive_group()
    run.add_argument("--once", action="store_true")
    run.add_argument("--loop", action="store_true")
    parser.add_argument("--bootstrap-existing", action="store_true",
                        help="테스트/명시적 백필 전용. 기본은 기존 글을 기준점으로만 삼는다.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.mode == "live":
        print("Live mentor signal trading is disabled by policy.", file=sys.stderr)
        return 2
    archive_path = Path(os.getenv("MENTOR_ARCHIVE_DB", PROJECT_ROOT / "data" / "archive.db"))
    state_path = Path(os.getenv("MENTOR_SIGNAL_STATE_DB", PROJECT_ROOT / "state" / "mentor_signals.db"))
    master_path_raw = os.getenv("MENTOR_STOCK_MASTER_PATH", "")
    if not master_path_raw:
        print("MENTOR_STOCK_MASTER_PATH is required", file=sys.stderr)
        return 2
    aliases_raw = os.getenv("MENTOR_STOCK_ALIASES_PATH", "")
    master = StockMasterSnapshot(Path(master_path_raw), Path(aliases_raw) if aliases_raw else None)
    notifier = send_telegram if telegram_configured() else None
    try:
        reader = MentorSignalReader(
            archive=ArchiveSource(archive_path), state=StateStore(state_path),
            parser=RuleParser(master), author_id=os.getenv("MENTOR_AUTHOR_ID", "").strip(),
            mode=args.mode,
            confidence_threshold=float(os.getenv("MENTOR_SIGNAL_CONFIDENCE_THRESHOLD", "0.95")),
            trading_base_url=os.getenv("TRADING_BOT_BASE_URL", ""),
            web_key=os.getenv("TRADING_BOT_WEB_KEY", ""), notifier=notifier,
        )
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.loop:
        reader.run_loop(int(os.getenv("MENTOR_SIGNAL_POLL_SECONDS", "60")))
        return 0
    print(json.dumps(reader.run_once(bootstrap_existing=args.bootstrap_existing), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
