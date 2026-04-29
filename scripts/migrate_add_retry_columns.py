"""scripts/migrate_add_retry_columns.py

articles 테이블에 재시도 추적 컬럼 3개 추가 + backfill.

추가 컬럼:
  attempt_count   INTEGER NOT NULL DEFAULT 0
  last_error_reason TEXT
  last_attempt_at TEXT  (ISO8601)

Backfill 규칙:
  BODY_COLLECTED  → attempt_count=1, last_attempt_at=updated_at (NULL-safe)
  BODY_FAILED/BODY_BLOCKED → attempt_count=1, last_error_reason='pre-migration: ...'
  INDEXED         → 기본값(0, NULL, NULL) 유지 — backfill 불필요

Idempotent:
  - 컬럼이 이미 있으면 ALTER 스킵
  - attempt_count=0 인 row만 backfill (재실행 시 덮어쓰지 않음)

실행 위치: C:/projects/naver_cafe_archive (프로젝트 루트)
"""
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "src")
from config import DB_PATH

DATA_DIR = DB_PATH.parent
PRE_MIGRATION_ERROR_REASON = "pre-migration: status was already failed/blocked"


def make_backup() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = DATA_DIR / f"archive_backup_{ts}_pre_retry_columns.db"
    shutil.copy2(DB_PATH, backup_path)
    print(f"[backup] {backup_path.name}")
    return backup_path


def get_existing_columns(conn: sqlite3.Connection) -> set:
    return {row[1] for row in conn.execute("PRAGMA table_info(articles)").fetchall()}


def run_migration(conn: sqlite3.Connection) -> None:
    existing = get_existing_columns(conn)

    if "attempt_count" not in existing:
        conn.execute(
            "ALTER TABLE articles ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0"
        )
        print("[alter] attempt_count 추가")
    else:
        print("[skip]  attempt_count 이미 존재")

    if "last_error_reason" not in existing:
        conn.execute("ALTER TABLE articles ADD COLUMN last_error_reason TEXT")
        print("[alter] last_error_reason 추가")
    else:
        print("[skip]  last_error_reason 이미 존재")

    if "last_attempt_at" not in existing:
        conn.execute("ALTER TABLE articles ADD COLUMN last_attempt_at TEXT")
        print("[alter] last_attempt_at 추가")
    else:
        print("[skip]  last_attempt_at 이미 존재")


def run_backfill(conn: sqlite3.Connection) -> None:
    # BODY_COLLECTED: attempt_count=1, last_attempt_at=updated_at (NULL-safe)
    r1 = conn.execute(
        """
        UPDATE articles
           SET attempt_count   = 1,
               last_attempt_at = updated_at
         WHERE status = 'BODY_COLLECTED'
           AND attempt_count = 0
        """
    )
    print(f"[backfill] BODY_COLLECTED  → {r1.rowcount}건 갱신")

    # BODY_FAILED / BODY_BLOCKED: attempt_count=1, last_error_reason 설정
    r2 = conn.execute(
        """
        UPDATE articles
           SET attempt_count    = 1,
               last_error_reason = ?
         WHERE status IN ('BODY_FAILED', 'BODY_BLOCKED')
           AND attempt_count = 0
        """,
        (PRE_MIGRATION_ERROR_REASON,),
    )
    print(f"[backfill] BODY_FAILED/BLOCKED → {r2.rowcount}건 갱신")

    # INDEXED: 기본값(0, NULL, NULL)이므로 별도 UPDATE 불필요
    indexed_count = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE status = 'INDEXED'"
    ).fetchone()[0]
    print(f"[backfill] INDEXED          → {indexed_count}건 기본값(0, NULL, NULL) 유지")


def print_summary(conn: sqlite3.Connection) -> None:
    print("\n[summary] status별 통계:")
    print(f"  {'status':<20} {'count':>6}  {'avg(attempt_count)':>18}")
    print(f"  {'-'*20}  {'-'*6}  {'-'*18}")
    rows = conn.execute(
        "SELECT status, COUNT(*), AVG(attempt_count) FROM articles GROUP BY status ORDER BY status"
    ).fetchall()
    for status, cnt, avg_att in rows:
        print(f"  {status:<20} {cnt:>6}  {avg_att:>18.2f}")


def main() -> None:
    if not DB_PATH.exists():
        print(f"[ERROR] DB 파일 없음: {DB_PATH}")
        sys.exit(1)

    backup_path = make_backup()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("BEGIN")
        run_migration(conn)
        run_backfill(conn)
        conn.execute("COMMIT")
        print("\n[OK] 마이그레이션 + backfill 완료")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"\n[ERROR] 예외 발생 — ROLLBACK 완료: {e}")
        print(f"[info]  복원: {backup_path.name} → archive.db 로 복사")
        conn.close()
        sys.exit(1)

    print_summary(conn)
    conn.close()

    print(f"\n[info] 백업 파일: {backup_path}")
    print("[info] 검증: python scripts/verify_retry_columns.py")


if __name__ == "__main__":
    main()
