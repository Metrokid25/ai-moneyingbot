"""Fixture -> Reader -> real Trading FastAPI -> watchlist -> Paper load_universe smoke."""
from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mentor_signal_reader import (  # noqa: E402
    ArchiveSource, MentorSignalReader, RuleParser, StateStore, StockMasterSnapshot,
)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def create_fixture(root: Path) -> tuple[Path, Path]:
    archive = root / "archive.db"
    con = sqlite3.connect(archive)
    posted = datetime.now(timezone(timedelta(hours=9))).isoformat()
    con.execute(
        "CREATE TABLE articles(article_id INTEGER PRIMARY KEY,title TEXT,url TEXT,author TEXT,"
        "posted_at TEXT,raw_html TEXT,clean_text TEXT,status TEXT,saved_at TEXT,updated_at TEXT)"
    )
    text = "오늘은 반도체 중에서도 SK하이닉스를 관심 있게 봅니다."
    con.execute(
        "INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?)",
        (173800, "오늘 시장 대응", "https://example/173800", "굿머닝",
         posted, text, text, "BODY_COLLECTED", posted, posted),
    )
    con.commit()
    con.close()
    master = root / "stock_master.json"
    master.write_text(
        json.dumps({"version": 3, "by_code": {"000660": "SK하이닉스"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    return archive, master


def wait_ready(url: str, process: subprocess.Popen, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"temporary Trading API exited rc={process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("temporary Trading API did not become ready")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trading-repo", type=Path, required=True)
    parser.add_argument("--trading-python", type=Path, required=True)
    args = parser.parse_args()
    port = free_port()
    # Windows may keep a terminated uvicorn SQLite handle briefly; cleanup failure must
    # not turn a fully successful smoke into a false negative.
    with tempfile.TemporaryDirectory(
        prefix="mentor-signal-e2e-", ignore_cleanup_errors=True
    ) as tmp:
        root = Path(tmp)
        archive, master_path = create_fixture(root)
        trading_db = root / "trading.db"
        child_env = os.environ.copy()
        child_env.update({
            "DB_PATH": str(trading_db),
            "WEB_SHARED_KEY": "e2e-key",
            "MENTOR_AUTHOR_ID": "굿머닝",
            "MENTOR_SIGNAL_CONFIDENCE_THRESHOLD": "0.95",
            "KIS_ENV": "PAPER",
            "PYTHONUTF8": "1",
        })
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        reader = None
        process = subprocess.Popen(
            [str(args.trading_python), "-m", "uvicorn", "webapp.server:app",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=args.trading_repo, env=child_env, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=creationflags,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            wait_ready(base_url + "/api/picks", process)
            state = StateStore(root / "state.db")
            # Fixture 한 건만 명시적으로 읽도록 상태를 구성한다. 운영 코드의
            # paper+bootstrap 안전 차단은 우회하지 않는다.
            state.initialize(last_article_id=0, last_scan_at="1970-01-01T00:00:00+00:00")
            reader = MentorSignalReader(
                archive=ArchiveSource(archive), state=state,
                parser=RuleParser(StockMasterSnapshot(master_path)), author_id="굿머닝",
                mode="paper", confidence_threshold=0.95, trading_base_url=base_url,
                web_key="e2e-key", notifier=None,
            )
            result = reader.run_once()
            con = sqlite3.connect(trading_db)
            audit = con.execute(
                "SELECT article_id,stock_code,delivery_status FROM mentor_signal_events"
            ).fetchall()
            watch = con.execute(
                "SELECT stock_code,stock_name,sector_name FROM sector_stocks"
            ).fetchall()
            con.close()
            verify_code = (
                "import json; from datetime import datetime,timedelta,timezone; "
                "from strategy.paper_runner import load_universe; "
                "d=datetime.now(timezone(timedelta(hours=9))).date(); "
                "print(json.dumps({'visible':load_universe(r'" + str(trading_db) + "'),"
                "'paper_today':load_universe(r'" + str(trading_db) + "',as_of_day=d),"
                "'paper_next':load_universe(r'" + str(trading_db) + "',as_of_day=d+timedelta(days=1))},"
                "ensure_ascii=False))"
            )
            verified = subprocess.run(
                [str(args.trading_python), "-c", verify_code], cwd=args.trading_repo,
                env=child_env, capture_output=True, text=True, encoding="utf-8", check=True,
            )
            universes = json.loads(verified.stdout.strip().splitlines()[-1])
            expected_watch = ["000660", "SK하이닉스", "멘토 자동픽 · 반도체"]
            expected_universe = ["000660", "SK하이닉스", "반도체"]
            if result["delivered"] != 1 or audit != [("173800", "000660", "registered")]:
                raise RuntimeError(f"delivery/audit mismatch: result={result} audit={audit}")
            if (watch != [tuple(expected_watch)]
                    or expected_universe not in universes["visible"]
                    or universes["paper_today"]
                    or expected_universe not in universes["paper_next"]):
                raise RuntimeError(f"watch/universe mismatch: watch={watch} universes={universes}")
            print(json.dumps({
                "reader": result, "signal": "ADD_WATCH", "audit": audit,
                "watchlist": watch, "paper_universe": universes, "live_order": "disabled",
            }, ensure_ascii=False))
        finally:
            if reader is not None:
                reader.archive.conn.close()
                reader.state.conn.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
