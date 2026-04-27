"""scripts/migrate_article_id_to_int.py

archive.db 의 article_id 컬럼을 TEXT → INTEGER 로 마이그레이션.

절차:
  1. data/archive.db → data/archive_old.db 로 rename
  2. db.init_db() → 새 INTEGER 스키마 archive.db 생성
  3. archive_old.db 에서 읽어서 새 DB에 article_id int() 변환 후 INSERT
  4. 정합성 체크 (row 수, typeof, 정렬)
  5. "MIGRATION OK" 출력
  실패 시 → abort, archive_old.db 복원 안내

실행 위치: C:/projects/naver_cafe_archive (프로젝트 루트)
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")

from config import DB_PATH
from db import init_db

OLD_DB = DB_PATH.parent / "archive_old.db"
BACKUP_DB = DB_PATH.parent / "archive_backup_20260427.db"


def abort(msg: str) -> None:
    print(f"\n[ABORT] {msg}")
    print(f"[ABORT] 원본 복원 방법:")
    print(f"  1. data/archive.db 를 삭제 (손상됐을 경우)")
    print(f"  2. data/archive_old.db → data/archive.db 로 rename")
    print(f"     또는: data/archive_backup_20260427.db → data/archive.db 로 복사")
    sys.exit(1)


def main() -> None:
    # 사전 조건 확인
    if not DB_PATH.exists():
        abort(f"archive.db 를 찾을 수 없습니다: {DB_PATH}")

    if not BACKUP_DB.exists():
        abort(f"백업 파일이 없습니다: {BACKUP_DB} — 백업 없이 마이그레이션 불가")

    if OLD_DB.exists():
        abort(f"archive_old.db 가 이미 존재합니다. 이전 실행 실패 흔적일 수 있습니다. "
              f"수동으로 확인 후 삭제하세요.")

    # 1. 기존 DB → archive_old.db 로 rename
    print(f"[step 1] {DB_PATH.name} → archive_old.db rename...")
    DB_PATH.rename(OLD_DB)
    print(f"  완료: {OLD_DB}")

    try:
        # 2. 새 INTEGER 스키마 DB 생성
        print(f"\n[step 2] init_db() → 새 INTEGER 스키마 생성...")
        init_db()
        if not DB_PATH.exists():
            abort("init_db() 후 archive.db 가 생성되지 않았습니다.")
        print(f"  완료: {DB_PATH}")

        # 3. 데이터 이관
        print(f"\n[step 3] 데이터 이관 (TEXT → INTEGER)...")
        old_conn = sqlite3.connect(OLD_DB)
        new_conn = sqlite3.connect(DB_PATH)
        old_conn.row_factory = sqlite3.Row

        rows = old_conn.execute("SELECT * FROM articles").fetchall()
        print(f"  읽은 행 수: {len(rows)}")

        insert_count = 0
        error_rows = []
        for row in rows:
            try:
                article_id_int = int(row["article_id"])
            except (ValueError, TypeError) as e:
                error_rows.append((row["article_id"], str(e)))
                continue

            new_conn.execute(
                """INSERT OR IGNORE INTO articles
                   (article_id, title, url, author, posted_at, raw_html, clean_text,
                    source_page, status, error_reason, saved_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    article_id_int,
                    row["title"],
                    row["url"],
                    row["author"],
                    row["posted_at"],
                    row["raw_html"],
                    row["clean_text"],
                    row["source_page"],
                    row["status"],
                    row["error_reason"],
                    row["saved_at"],
                    row["updated_at"],
                ),
            )
            insert_count += 1

        new_conn.commit()
        old_conn.close()

        if error_rows:
            print(f"\n[WARN] int() 변환 실패 행 {len(error_rows)}건:")
            for aid, err in error_rows:
                print(f"  article_id={aid!r}: {err}")
            abort("변환 실패 행이 존재합니다. 데이터를 확인하세요.")

        print(f"  이관 완료: {insert_count}건")

        # 4. 정합성 체크
        print(f"\n[step 4] 정합성 체크...")
        old_count = sqlite3.connect(OLD_DB).execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        new_count = new_conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        print(f"  row 수 — old: {old_count}  new: {new_count}")
        if old_count != new_count:
            abort(f"행 수 불일치: old={old_count} != new={new_count}")

        types = new_conn.execute(
            "SELECT typeof(article_id), COUNT(*) FROM articles GROUP BY typeof(article_id)"
        ).fetchall()
        print(f"  typeof(article_id) 분포: {types}")
        if types != [("integer", new_count)]:
            abort(f"article_id 타입이 integer 단일이 아닙니다: {types}")

        min_id, max_id = new_conn.execute(
            "SELECT MIN(article_id), MAX(article_id) FROM articles"
        ).fetchone()
        print(f"  MIN(article_id)={min_id}  MAX(article_id)={max_id}")

        new_conn.close()
        print(f"\n{'='*50}")
        print(f"  MIGRATION OK")
        print(f"{'='*50}")
        print(f"\n[info] archive_old.db 는 검증 통과 확인 후 수동 삭제하세요.")

    except Exception as e:
        print(f"\n[ERROR] 예외 발생: {e}")
        abort("예외가 발생했습니다.")


if __name__ == "__main__":
    main()
