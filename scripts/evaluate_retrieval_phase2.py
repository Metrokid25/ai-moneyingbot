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
    EVALUATION_QUERIES,
    build_eval_record,
    embed_query,
    format_search_results,
    get_collection_summary,
    open_qdrant_client,
    search_qdrant,
    validate_eval_queries,
    validate_output_path,
    validate_run_mode,
    validate_top_k,
    write_jsonl,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_PATH = PROJECT_ROOT / "data" / "retrieval_eval_phase2.jsonl"


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Phase 2 Qdrant retrieval quality")
    parser.add_argument("--qdrant-path", type=Path, default=PROJECT_ROOT / DEFAULT_QDRANT_PATH)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def select_queries(queries: list[str], limit: int | None) -> list[str]:
    if limit is None:
        return queries
    if limit < 0:
        raise ValueError("--limit must be non-negative")
    return queries[:limit]


def print_summary(summary: dict[str, Any]) -> None:
    print("=== Phase 2 retrieval evaluation summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")


def main() -> int:
    configure_output_encoding()
    args = parse_args()
    try:
        validate_top_k(args.top_k)
        validate_run_mode(dry_run=args.dry_run, execute=args.execute)
        if args.overwrite and not args.execute:
            validate_output_path(args.out, overwrite=args.overwrite, execute=args.execute)
        validate_eval_queries(EVALUATION_QUERIES)
        queries = select_queries(EVALUATION_QUERIES, args.limit)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    client = open_qdrant_client(args.qdrant_path)
    collection_summary = get_collection_summary(client, args.collection)
    if not collection_summary["collection_exists"]:
        print(f"[ERROR] collection {args.collection} does not exist", file=sys.stderr)
        return 1

    summary = {
        "query_count": len(queries),
        "total_query_count": len(EVALUATION_QUERIES),
        "top_k": args.top_k,
        "model": args.model,
        "qdrant_path": str(args.qdrant_path),
        "collection": args.collection,
        "out": str(args.out),
        "dry_run": bool(args.dry_run),
        "execute": bool(args.execute),
        "overwrite": bool(args.overwrite),
    }
    summary.update(collection_summary)

    if args.dry_run:
        print_summary(summary)
        print("=== Evaluation queries ===")
        for index, query in enumerate(queries, 1):
            print(f"{index:02d}. {query}")
        return 0

    records: list[dict[str, Any]] = []
    try:
        validate_output_path(args.out, overwrite=args.overwrite, execute=args.execute)
        for query in queries:
            query_vector = embed_query(query, model=args.model, project_root=PROJECT_ROOT)
            points = search_qdrant(
                client=client,
                collection=args.collection,
                query_vector=query_vector,
                top_k=args.top_k,
            )
            records.append(
                build_eval_record(
                    query=query,
                    results=format_search_results(points),
                    top_k=args.top_k,
                )
            )
        write_jsonl(args.out, records, overwrite=args.overwrite)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    summary["written_records"] = len(records)
    print_summary(summary)
    for record in records:
        top = record["results"][0] if record["results"] else {}
        print(f"query: {record['query']}")
        print(f"top_title: {top.get('title')}")
        print(f"top_score: {top.get('score')}")
        print(f"top_chunk_id: {top.get('chunk_id')}")
        print("---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
