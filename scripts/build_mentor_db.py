"""Build a self-contained, queryable SQLite of the full mentor corpus.

Reads data/normalized_articles.jsonl (the full clean_text of every archived
article) and writes data/mentor.db: one `articles` table with all metadata +
full body, plus a trigram FTS5 index for fast substring search. This is the
"look at the whole corpus" DB for Claude/tools on the laptop — it pairs with the
qdrant semantic index (data/qdrant). Read-only in use; regenerate from a fresh
jsonl export when the PC re-collects.

Search cheatsheet (run these against mentor.db):
  - 2-char / any substring:  SELECT article_id,title,posted_at FROM articles
                             WHERE clean_text LIKE '%손절%';
  - ranked full-text (>=3 chars, faster):
        SELECT a.article_id, a.title, a.posted_at
        FROM articles_fts f JOIN articles a ON a.article_id = f.rowid
        WHERE articles_fts MATCH '장대양봉' ORDER BY rank;
  - read one article:  SELECT clean_text FROM articles WHERE article_id = 28832;
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = PROJECT_ROOT / "data" / "normalized_articles.jsonl"
DEFAULT_OUT = PROJECT_ROOT / "data" / "mentor.db"

COLUMNS = [
    "article_id", "title", "clean_text", "posted_at", "created_at",
    "collected_at", "url", "source_url", "author", "source", "content_hash", "status",
]

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass


def iter_rows(src: Path, stats: dict):
    with src.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            stats["lines"] += 1
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                stats["bad_json"] += 1
                continue
            try:
                aid = int(d["article_id"])
            except (KeyError, TypeError, ValueError):
                stats["bad_id"] += 1
                continue
            yield (aid, *[d.get(c) for c in COLUMNS[1:]])


def _cleanup(out: Path) -> None:
    for p in (out, Path(f"{out}-wal"), Path(f"{out}-shm")):
        if p.exists():
            p.unlink()


def build(src: Path, out: Path) -> int:
    _cleanup(out)  # drop mentor.db plus any stale -wal/-shm from a prior crashed run
    con = sqlite3.connect(str(out))
    stats = {"lines": 0, "bad_json": 0, "bad_id": 0}
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(
            "CREATE TABLE articles ("
            "article_id INTEGER PRIMARY KEY, title TEXT, clean_text TEXT, "
            "posted_at TEXT, created_at TEXT, collected_at TEXT, url TEXT, "
            "source_url TEXT, author TEXT, source TEXT, content_hash TEXT, status TEXT)"
        )
        placeholders = ",".join("?" for _ in COLUMNS)
        n = 0
        batch = []
        for row in iter_rows(src, stats):
            batch.append(row)
            if len(batch) >= 2000:
                con.executemany(f"INSERT OR IGNORE INTO articles VALUES ({placeholders})", batch)
                n += len(batch)
                batch = []
        if batch:
            con.executemany(f"INSERT OR IGNORE INTO articles VALUES ({placeholders})", batch)
            n += len(batch)

        con.execute("CREATE INDEX idx_posted_at ON articles(posted_at)")

        fts_ok = True
        try:
            con.execute(
                "CREATE VIRTUAL TABLE articles_fts USING fts5("
                "title, clean_text, content='articles', content_rowid='article_id', "
                "tokenize='trigram')"
            )
            con.execute(
                "INSERT INTO articles_fts(rowid, title, clean_text) "
                "SELECT article_id, title, clean_text FROM articles"
            )
        except sqlite3.OperationalError as exc:
            fts_ok = False
            print(f"warning: trigram FTS unavailable ({exc}); LIKE search still works.")

        con.commit()
        con.execute("PRAGMA optimize")
        # Collapse WAL back into the main file so mentor.db is a single, movable file.
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("PRAGMA journal_mode=DELETE")

        total = con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        # Surface every way rows can go missing (silent loss is the real risk here).
        if stats["bad_json"] or stats["bad_id"]:
            print(f"warning: skipped {stats['bad_json']} malformed-JSON + "
                  f"{stats['bad_id']} bad-article_id row(s) — NOT in DB")
        if n != total:
            print(f"warning: {n - total} duplicate article_id row(s) dropped by OR IGNORE")
        if fts_ok:
            fts_n = con.execute("SELECT COUNT(*) FROM articles_fts").fetchone()[0]
            con.execute("INSERT INTO articles_fts(articles_fts) VALUES('integrity-check')")  # raises if corrupt
            if fts_n != total:
                print(f"warning: FTS rows {fts_n} != articles {total} — index under-populated")
        print(f"read {stats['lines']} lines | inserted {n} | articles: {total} | "
              f"fts: {'on (trigram)' if fts_ok else 'off'}")
        return total
    except BaseException:
        con.close()
        _cleanup(out)  # never leave a half-built DB that looks complete
        raise
    finally:
        con.close()


def smoke(out: Path, term: str) -> None:
    con = sqlite3.connect(str(out))
    try:
        like = con.execute(
            "SELECT COUNT(*) FROM articles WHERE clean_text LIKE ?", (f"%{term}%",)
        ).fetchone()[0]
        print(f"\nLIKE '%{term}%' -> {like} articles")
        rows = con.execute(
            "SELECT article_id, posted_at, substr(title,1,30) FROM articles "
            "WHERE clean_text LIKE ? ORDER BY posted_at LIMIT 5", (f"%{term}%",)
        ).fetchall()
        for r in rows:
            print(f"  #{r[0]} ({r[1]}) {r[2]}")
    finally:
        con.close()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", type=Path, default=DEFAULT_SRC)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--smoke-term", default="손절")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.src.exists():
        print(f"error: source not found: {args.src}")
        return 1
    build(args.src, args.out)
    smoke(args.out, args.smoke_term)
    size_mb = args.out.stat().st_size / 1_000_000
    print(f"\nwrote {args.out} ({size_mb:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
