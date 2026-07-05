"""Export Archive Bot articles to the RAG ingest-contract JSONL.

Read-only consumer of the Archive Bot database. This script never writes to or
mutates archive.db; it only reads BODY_COLLECTED articles and emits the JSONL
contract expected by scripts/ingest_archive_export.py. See
docs/rag_ingest_boundary.md (read-only consumption is activated).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterator


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "archive.db"
DEFAULT_OUT_PATH = PROJECT_ROOT / "exports" / "archive_articles.jsonl"
DEFAULT_SOURCE = "naver_cafe"

# Fields required by scripts/ingest_archive_export.py REQUIRED_FIELDS.
EXPORT_FIELDS = (
    "article_id",
    "title",
    "body_text",
    "url",
    "author",
    "created_at",
    "collected_at",
    "source",
    "content_hash",
)


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def content_hash_for(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def fetch_rows(db_path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    """Read BODY_COLLECTED articles from archive.db in read-only mode."""
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT article_id, title, url, author, posted_at, clean_text, saved_at, updated_at
            FROM articles
            WHERE status = 'BODY_COLLECTED'
            ORDER BY article_id
        """
        params: list[Any] = []
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def build_export_record(row: dict[str, Any], source: str = DEFAULT_SOURCE) -> dict[str, Any] | None:
    """Map an archive.db row to the ingest contract, or None if not exportable."""
    title = normalize(row.get("title"))
    body_text = normalize(row.get("clean_text"))
    url = normalize(row.get("url"))
    author = normalize(row.get("author"))
    created_at = normalize(row.get("posted_at")) or normalize(row.get("saved_at"))
    collected_at = (
        normalize(row.get("saved_at"))
        or normalize(row.get("updated_at"))
        or normalize(row.get("posted_at"))
    )
    try:
        article_id = None if row.get("article_id") is None else int(row.get("article_id"))
    except (TypeError, ValueError):
        return None

    if article_id is None or not title or not body_text or not url or not author:
        return None
    if not created_at or not collected_at:
        return None

    return {
        "article_id": article_id,
        "title": title,
        "body_text": body_text,
        "url": url,
        "author": author,
        "created_at": created_at,
        "collected_at": collected_at,
        "source": source,
        "content_hash": content_hash_for(body_text),
    }


def iter_export_records(
    rows: list[dict[str, Any]], source: str = DEFAULT_SOURCE
) -> Iterator[dict[str, Any]]:
    for row in rows:
        record = build_export_record(row, source=source)
        if record is not None:
            yield record


def write_jsonl(path: Path, records: list[dict[str, Any]], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass --overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only export of Archive Bot articles to the RAG ingest-contract JSONL.",
        epilog="Read-only: never writes to archive.db. See docs/rag_ingest_boundary.md.",
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--out-path", type=Path, default=DEFAULT_OUT_PATH)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    if args.limit is not None and args.limit < 0:
        print("[ERROR] --limit must be non-negative", file=sys.stderr)
        return 2
    if not args.db_path.exists():
        print(f"[ERROR] archive db not found: {args.db_path}", file=sys.stderr)
        return 1

    try:
        rows = fetch_rows(args.db_path, args.limit)
    except (OSError, sqlite3.Error) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    records = list(iter_export_records(rows, source=args.source))
    skipped = len(rows) - len(records)

    if not args.dry_run:
        try:
            write_jsonl(args.out_path, records, args.overwrite)
        except (OSError, FileExistsError) as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1

    print("=== Archive export summary ===")
    print(f"db_path: {args.db_path}")
    print(f"rows_read: {len(rows)}")
    print(f"exported: {len(records)}")
    print(f"skipped_incomplete: {skipped}")
    print(f"out_path: {None if args.dry_run else args.out_path}")
    print(f"dry_run: {bool(args.dry_run)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
