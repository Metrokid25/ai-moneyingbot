"""로그 파일의 네이버 세션 쿠키 등 비밀을 마스킹(스크럽).

run_daily_archive_loop.redact_secrets를 재사용한다. 일회성 정리 + 필요 시 재실행 가능.
사용: python scripts/scrub_log_secrets.py [로그디렉터리(기본 logs)]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_daily_archive_loop import redact_secrets

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("logs")
scrubbed = 0
scanned = 0
for f in root.rglob("*.log"):
    scanned += 1
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        print(f"[skip] {f}: {exc}")
        continue
    redacted = redact_secrets(text)
    if redacted != text:
        f.write_text(redacted, encoding="utf-8")
        scrubbed += 1
        print(f"[scrubbed] {f}")
print(f"[scrub] scanned={scanned} scrubbed={scrubbed}")
