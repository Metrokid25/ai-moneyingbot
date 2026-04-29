"""scripts/verify_retry_columns.py

migrate_add_retry_columns.py 실행 후 검증 스크립트.

검증 항목:
  1. 3개 컬럼(attempt_count, last_error_reason, last_attempt_at) 존재 여부
  2. 컬럼 타입 (INTEGER, TEXT, TEXT)
  3. BODY_COLLECTED 전체가 attempt_count = 1 인지
  4. INDEXED 전체가 attempt_count = 0 인지
  5. 총 row 수가 가장 최근 pre_retry_columns 백업과 동일한지

각 항목 PASS/FAIL 출력. 하나라도 FAIL이면 exit 1.

실행 위치: C:/projects/naver_cafe_archive (프로젝트 루트)
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "src")
from config import DB_PATH

DATA_DIR = DB_PATH.parent

PASS = "PASS"
FAIL = "FAIL"

results: list[tuple[str, str]] = []


def check(label: str, passed: bool, detail: str = "") -> bool:
    tag = PASS if passed else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{tag}] {label}{suffix}")
    results.append((label, tag))
    return passed


def find_latest_backup() -> Path | None:
    candidates = sorted(
        DATA_DIR.glob("archive_backup_*_pre_retry_columns.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def main() -> None:
    if not DB_PATH.exists():
        print(f"[ERROR] DB 파일 없음: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    print(f"DB: {DB_PATH}\n")

    # 1. 컬럼 존재 여부
    col_info = {
        row[1]: row[2]
        for row in conn.execute("PRAGMA table_info(articles)").fetchall()
    }
    check("attempt_count 컬럼 존재", "attempt_count" in col_info)
    check("last_error_reason 컬럼 존재", "last_error_reason" in col_info)
    check("last_attempt_at 컬럼 존재", "last_attempt_at" in col_info)

    # 이후 검증은 컬럼이 존재할 때만 의미 있음
    columns_ok = all(
        c in col_info
        for c in ("attempt_count", "last_error_reason", "last_attempt_at")
    )

    if not columns_ok:
        print("\n컬럼이 없어 이후 검증을 건너뜁니다. 마이그레이션을 먼저 실행하세요.")
        conn.close()
        sys.exit(1)

    # 2. 컬럼 타입
    check(
        "attempt_count 타입 = INTEGER",
        col_info["attempt_count"].upper() == "INTEGER",
        col_info["attempt_count"],
    )
    check(
        "last_error_reason 타입 = TEXT",
        col_info["last_error_reason"].upper() == "TEXT",
        col_info["last_error_reason"],
    )
    check(
        "last_attempt_at 타입 = TEXT",
        col_info["last_attempt_at"].upper() == "TEXT",
        col_info["last_attempt_at"],
    )

    # 3. BODY_COLLECTED: 전부 attempt_count = 1
    body_collected_total = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE status = 'BODY_COLLECTED'"
    ).fetchone()[0]
    body_collected_ok = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE status = 'BODY_COLLECTED' AND attempt_count = 1"
    ).fetchone()[0]
    check(
        "BODY_COLLECTED 전체 attempt_count = 1",
        body_collected_total == body_collected_ok,
        f"{body_collected_ok}/{body_collected_total}건",
    )

    # 4. INDEXED: 전부 attempt_count = 0
    indexed_total = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE status = 'INDEXED'"
    ).fetchone()[0]
    indexed_ok = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE status = 'INDEXED' AND attempt_count = 0"
    ).fetchone()[0]
    check(
        "INDEXED 전체 attempt_count = 0",
        indexed_total == indexed_ok,
        f"{indexed_ok}/{indexed_total}건",
    )

    # 5. 총 row 수 = 백업 DB row 수
    current_total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    backup_path = find_latest_backup()
    if backup_path is None:
        check(
            f"총 row 수 백업 대비 동일 (현재 {current_total}건)",
            False,
            "pre_retry_columns 백업 파일 없음",
        )
    else:
        backup_total = sqlite3.connect(backup_path).execute(
            "SELECT COUNT(*) FROM articles"
        ).fetchone()[0]
        check(
            f"총 row 수 동일 (백업: {backup_path.name})",
            current_total == backup_total,
            f"현재={current_total}  백업={backup_total}",
        )

    conn.close()

    # 결과 집계
    failed = [label for label, tag in results if tag == FAIL]
    print(f"\n결과: {len(results) - len(failed)}/{len(results)} PASS")
    if failed:
        print("FAIL 항목:")
        for label in failed:
            print(f"  - {label}")
        sys.exit(1)

    print("ALL PASS")


if __name__ == "__main__":
    main()
