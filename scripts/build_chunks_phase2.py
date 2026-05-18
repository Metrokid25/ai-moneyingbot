import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_chunking import REQUIRED_METADATA_FIELDS, build_chunk_records


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "archive.db"
DEFAULT_OUT_PATH = PROJECT_ROOT / "data" / "chunks_phase2.jsonl"


def fetch_articles(db_path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT article_id, title, posted_at, author, clean_text, status
            FROM articles
            WHERE status = 'BODY_COLLECTED'
            ORDER BY article_id
        """
        params: list[Any] = []
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def build_chunks(
    articles: list[dict[str, Any]],
    threshold: int,
    chunk_size: int,
    overlap: int,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for article in articles:
        records = build_chunk_records(
            article,
            threshold=threshold,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        chunks.extend(records)
    return chunks


def summarize(articles: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> dict[str, Any]:
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    chunk_id_counts = Counter(chunk_ids)
    chunks_by_article: dict[int, list[int]] = defaultdict(list)
    missing_metadata = 0

    for chunk in chunks:
        article_id = int(chunk["article_id"])
        chunks_by_article[article_id].append(int(chunk["chunk_index"]))
        if set(chunk["metadata"]) < REQUIRED_METADATA_FIELDS:
            missing_metadata += 1

    chunks_per_article = [len(v) for v in chunks_by_article.values()]
    discontinuous = 0
    for indexes in chunks_by_article.values():
        sorted_indexes = sorted(indexes)
        if sorted_indexes != list(range(len(sorted_indexes))):
            discontinuous += 1

    return {
        "processed_articles": len(articles),
        "total_chunks": len(chunks),
        "duplicate_chunk_ids": sum(count - 1 for count in chunk_id_counts.values() if count > 1),
        "empty_embedding_text_count": sum(
            1 for chunk in chunks if not (chunk.get("embedding_text") or "").strip()
        ),
        "body_len_0_articles": sum(1 for article in articles if len(article.get("clean_text") or "") == 0),
        "min_chunks_per_article": min(chunks_per_article) if chunks_per_article else 0,
        "max_chunks_per_article": max(chunks_per_article) if chunks_per_article else 0,
        "articles_with_multiple_chunks": sum(1 for count in chunks_per_article if count > 1),
        "articles_with_discontinuous_chunk_index": discontinuous,
        "chunks_missing_required_metadata": missing_metadata,
    }


def write_jsonl(out_path: Path, chunks: list[dict[str, Any]], overwrite: bool) -> None:
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"{out_path} already exists; pass --overwrite to replace it")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Phase 2 RAG chunks JSONL")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--out-path", type=Path, default=DEFAULT_OUT_PATH)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--threshold", type=int, default=1500)
    parser.add_argument("--chunk-size", type=int, default=1100)
    parser.add_argument("--overlap", type=int, default=180)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 0:
        print("[ERROR] --limit must be non-negative", file=sys.stderr)
        return 2

    if args.out_path.exists() and not args.overwrite and not args.dry_run:
        print(f"[ERROR] {args.out_path} already exists; pass --overwrite", file=sys.stderr)
        return 1

    articles = fetch_articles(args.db_path, args.limit)
    chunks = build_chunks(
        articles,
        threshold=args.threshold,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
    summary = summarize(articles, chunks)
    summary["output_path"] = str(args.out_path)
    summary["dry_run"] = bool(args.dry_run)

    if not args.dry_run:
        try:
            write_jsonl(args.out_path, chunks, args.overwrite)
        except FileExistsError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1

    print("=== Phase 2 chunk build summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
