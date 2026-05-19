import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_retrieval import (
    DEFAULT_COLLECTION,
    DEFAULT_MODEL,
    DEFAULT_QDRANT_PATH,
    DEFAULT_TOP_K,
    embed_query,
    format_search_results,
    get_collection_summary,
    open_qdrant_client,
    search_qdrant,
    validate_run_mode,
    validate_top_k,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search Phase 2 Qdrant chunk collection")
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--qdrant-path", type=Path, default=PROJECT_ROOT / DEFAULT_QDRANT_PATH)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def print_summary(summary: dict[str, Any]) -> None:
    print("=== Phase 2 Qdrant retrieval summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")


def print_results(results: list[dict[str, Any]]) -> None:
    print("=== Search results ===")
    for row in results:
        print(f"rank: {row['rank']}")
        print(f"score: {row['score']}")
        print(f"chunk_id: {row['chunk_id']}")
        print(f"article_id: {row['article_id']}")
        print(f"posted_at: {row['posted_at']}")
        print(f"title: {row['title']}")
        print(f"snippet: {row['snippet']}")
        print(f"source: {row['source']}")
        print("---")


def main() -> int:
    configure_output_encoding()
    args = parse_args()
    try:
        validate_top_k(args.top_k)
        validate_run_mode(dry_run=args.dry_run, execute=args.execute)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    client = open_qdrant_client(args.qdrant_path)
    collection_summary = get_collection_summary(client, args.collection)
    if not collection_summary["collection_exists"]:
        print(f"[ERROR] collection {args.collection} does not exist", file=sys.stderr)
        return 1

    summary = {
        "query": args.query,
        "top_k": args.top_k,
        "model": args.model,
        "qdrant_path": str(args.qdrant_path),
        "collection": args.collection,
        "dry_run": bool(args.dry_run),
        "execute": bool(args.execute),
    }
    summary.update(collection_summary)

    if args.dry_run:
        print_summary(summary)
        return 0

    try:
        query_vector = embed_query(args.query, model=args.model, project_root=PROJECT_ROOT)
        points = search_qdrant(
            client=client,
            collection=args.collection,
            query_vector=query_vector,
            top_k=args.top_k,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    summary["query_vector_size"] = len(query_vector)
    summary["results_count"] = len(points)
    print_summary(summary)
    print_results(format_search_results(points))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
