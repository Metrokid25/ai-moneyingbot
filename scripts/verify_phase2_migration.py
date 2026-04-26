import sqlite3
import sys
sys.path.insert(0, "src")
from config import DB_PATH

conn = sqlite3.connect(DB_PATH)

# 1. PRAGMA table_info
print("=== COLUMNS ===")
cols = conn.execute("PRAGMA table_info(articles)").fetchall()
for c in cols:
    print(f"  cid={c[0]:2d}  {c[1]:15s} {c[2]:10s} notnull={c[3]} default={c[4]}")

# 2. Row count
total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
print(f"\n=== TOTAL ROWS: {total} ===")

# 3. Status breakdown
print("\n=== STATUS BREAKDOWN ===")
rows = conn.execute(
    "SELECT status, COUNT(*) FROM articles GROUP BY status"
).fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]}")

# 4. updated_at NULL check (backfill 누락 검증)
null_count = conn.execute(
    "SELECT COUNT(*) FROM articles WHERE updated_at IS NULL"
).fetchone()[0]
print(f"\n=== updated_at NULL count: {null_count} (expected: 0) ===")

# 5. saved_at != updated_at mismatch (backfill 정확성)
mismatch = conn.execute(
    "SELECT COUNT(*) FROM articles WHERE saved_at != updated_at"
).fetchone()[0]
print(f"=== saved_at != updated_at count: {mismatch} (expected: 0) ===")

# 6. 샘플 5건 raw view
print("\n=== SAMPLE 5 ROWS ===")
sample = conn.execute(
    "SELECT article_id, status, saved_at, updated_at FROM articles "
    "ORDER BY article_id LIMIT 5"
).fetchall()
for s in sample:
    print(f"  id={s[0]:6s}  status={s[1]:10s}  saved={s[2]}  updated={s[3]}")

# 7. article_id=53 단건 조회 (신규 함수 테스트)
print("\n=== TEST: get_article_by_id('53') ===")
from db import get_article_by_id
a = get_article_by_id("53")
if a is None:
    print("  None")
else:
    print(f"  article_id={a.article_id}")
    print(f"  status={a.status}")
    print(f"  title={a.title[:40] if a.title else None}")
    print(f"  saved_at={a.saved_at}")
    print(f"  updated_at={a.updated_at}")
    print(f"  saved_at == updated_at: {a.saved_at == a.updated_at}")

# 8. 존재하지 않는 ID 테스트
print("\n=== TEST: get_article_by_id('nonexistent_999999') ===")
b = get_article_by_id("nonexistent_999999")
print(f"  result: {b}")

# 9. get_articles_by_status('INDEXED', limit=3)
print("\n=== TEST: get_articles_by_status('INDEXED', limit=3) ===")
from db import get_articles_by_status
items = get_articles_by_status("INDEXED", limit=3)
for it in items:
    print(f"  id={it.article_id}  status={it.status}")

conn.close()
print("\n=== DONE ===")
