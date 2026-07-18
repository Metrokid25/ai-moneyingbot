"""매일 '오늘 수집 요약' 텔레그램 알림. RAG 텔레그램(notify_telegram)을 재사용한다.

'오늘 수집'은 오늘(KST) 상주 루프 로그의 사이클별 saved_delta 합으로 센다.
이유: 16GB archive.db를 saved_at으로 풀스캔하면 느리다(인덱스 없음). 로그 합산은 즉시.
누적 총계/최신 article_id는 read-only 요약(COUNT(*)+MAX)을 쓴다.

토큰/채널: RAG_TELEGRAM_BOT_TOKEN/CHAT_ID(.env). 새 env 키 없음. notify_telegram.py 미수정.
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from run_daily_archive_loop import DEFAULT_DB_FILE, DEFAULT_LOG_DIR, readonly_archive_summary

KST = timezone(timedelta(hours=9))
ALERT_PREFIX = "[Archive] 일일 수집 요약"
# 사이클 전체 델타 라인만 센다. 주의: append_log는 같은 내용을 축약한 'stdout_summary:'
# 라인으로도 한 번 더 쓴다 → stdout 원문의 사이클 라인('[archive_loop] cycle N finished:')에
# 앵커링(match)해 이중 카운트를 막는다. (스텝별 'title collection finished:'도 자연 제외.)
_CYCLE_SAVED_RE = re.compile(r"\[archive_loop\]\s+cycle\s+\d+\s+finished:.*saved_delta=(\d+)")


def today_saved_count(log_dir: Path, day: date) -> int:
    """오늘(KST) 로그의 사이클별 saved_delta 합. 로그 없으면 0."""
    log_path = log_dir / f"{day.isoformat()}.log"
    if not log_path.exists():
        return 0
    total = 0
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _CYCLE_SAVED_RE.match(line.lstrip())
        if m:
            total += int(m.group(1))
    return total


def build_message(day: date, today_saved: int, total_count, latest_id) -> str:
    total_str = f"{total_count:,}건" if isinstance(total_count, int) else "확인불가"
    latest_str = str(latest_id) if latest_id is not None else "확인불가"
    return (
        f"{ALERT_PREFIX}\n"
        f"{day.isoformat()} (KST) 기준\n"
        f"오늘 수집: {today_saved:,}건\n"
        f"누적 총계: {total_str}\n"
        f"최신 글 id: {latest_str}"
    )


def main() -> int:
    day = datetime.now(KST).date()
    today_saved = today_saved_count(DEFAULT_LOG_DIR, day)
    try:
        summary = readonly_archive_summary(DEFAULT_DB_FILE)
    except Exception as exc:  # DB 조회 실패해도 알림은 보낸다(오늘 수집 건수는 로그 기반)
        print(f"[daily_summary] WARN: archive summary failed: {exc}")
        summary = {"article_count": None, "latest_article_id": None}

    text = build_message(
        day, today_saved, summary.get("article_count"), summary.get("latest_article_id")
    )

    from notify_telegram import send_telegram  # 지연 import: .env 로드 후 토큰 읽기

    sent_ok = send_telegram(text)
    print(f"[daily_summary] {day} saved={today_saved} total={summary.get('article_count')} sent_ok={sent_ok}")
    return 0 if sent_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
