"""로그 파일의 네이버 세션 쿠키 등 비밀을 마스킹(스크럽).

run_daily_archive_loop.redact_secrets를 재사용한다. 과거(수정 전) 로그 정리용.
신규 로그는 append_log가 write-time 레닥션을 적용하므로 비밀이 남지 않는다.

주의:
- **오늘(KST) 로그는 스킵**한다 — 상주 루프가 실시간 append 중이라 읽고-통째로-다시쓰면
  그 사이 append된 사이클이 유실된다(일일 요약이 그 saved_delta에 의존). 오늘 로그는 어차피
  write-time 레닥션 적용분이라 비밀도 없다.
- 완전한 과거 정리를 원하면 봇을 멈춘 뒤 실행하라.

사용: python scripts/scrub_log_secrets.py [로그디렉터리(기본 logs)]
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_daily_archive_loop import redact_secrets

KST = timezone(timedelta(hours=9))
_today_log_name = f"{datetime.now(KST).date().isoformat()}.log"

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("logs")
scanned = scrubbed = skipped_live = 0
for f in root.rglob("*.log"):
    scanned += 1
    if f.name == _today_log_name:
        skipped_live += 1
        print(f"[skip-live] {f} (오늘 로그: 라이브 append 레이스 방지, 이미 레닥션 적용됨)")
        continue
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        print(f"[skip] read failed {f}: {exc}")
        continue
    redacted = redact_secrets(text)
    if redacted == text:
        continue
    try:
        f.write_text(redacted, encoding="utf-8")
    except Exception as exc:  # 한 파일 실패가 전체 중단시키지 않게(나머지 계속 스크럽)
        print(f"[skip] write failed {f}: {exc}")
        continue
    scrubbed += 1
    print(f"[scrubbed] {f}")

print(f"[scrub] scanned={scanned} scrubbed={scrubbed} skipped_live={skipped_live}")
