import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_answer_context import (
    DEFAULT_CONTEXT_TOP_K,
    build_context_items,
    format_context_json,
    format_context_markdown,
    validate_context_top_k,
    validate_output_path,
    write_text_output,
)
from rag_retrieval import (
    DEFAULT_COLLECTION,
    DEFAULT_MODEL,
    DEFAULT_QDRANT_PATH,
    embed_query,
    get_collection_summary,
    open_qdrant_client,
    search_qdrant,
    validate_run_mode,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Phase 2 RAG answer context from Qdrant results")
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=DEFAULT_CONTEXT_TOP_K)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--qdrant-path", type=Path, default=PROJECT_ROOT / DEFAULT_QDRANT_PATH)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def print_summary(summary: dict[str, Any]) -> None:
    print("=== Phase 2 answer context builder summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")


def ensure_query(query: str) -> None:
    if not query.strip():
        raise ValueError("--query must not be empty")


def ensure_collection_ready(summary: dict[str, Any], collection: str) -> None:
    if not summary["collection_exists"]:
        raise RuntimeError(f"collection {collection} does not exist")
    points_count = summary.get("points_count")
    if points_count is None or int(points_count) <= 0:
        raise RuntimeError(f"collection {collection} has no points")
    status = str(summary.get("status", "")).lower()
    if status != "green":
        raise RuntimeError(f"collection {collection} status is not green: {summary.get('status')}")


def render_context(question: str, results: list[dict[str, Any]], top_k: int, output_format: str) -> str:
    if output_format == "json":
        return format_context_json(question, results, top_k)
    return format_context_markdown(question, results, top_k)


def main() -> int:
    configure_output_encoding()
    args = parse_args()
    try:
        ensure_query(args.query)
        validate_context_top_k(args.top_k)
        validate_run_mode(dry_run=args.dry_run, execute=args.execute)
        if args.dry_run and args.out is not None:
            raise ValueError("--dry-run must not create output files; omit --out")
        if args.out is not None and not args.dry_run:
            validate_output_path(args.out, overwrite=args.overwrite)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    client = open_qdrant_client(args.qdrant_path)
    collection_summary = get_collection_summary(client, args.collection)
    try:
        ensure_collection_ready(collection_summary, args.collection)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    summary = {
        "query": args.query,
        "top_k": args.top_k,
        "format": args.format,
        "model": args.model,
        "qdrant_path": str(args.qdrant_path),
        "collection": args.collection,
        "out": str(args.out) if args.out else None,
        "dry_run": bool(args.dry_run),
        "execute": bool(args.execute),
        "overwrite": bool(args.overwrite),
        "voyage_api_call": bool(args.execute),
        "qdrant_operation": "read/search only",
    }
    summary.update(collection_summary)

    if args.dry_run:
        print_summary(summary)
        print("=== Execution plan ===")
        print("1. Validate query and top_k.")
        print("2. Embed the query with Voyage only when --execute is used.")
        print("3. Search Qdrant top_k with payloads and without vectors.")
        print("4. Render answer context; no final LLM answer is generated.")
        return 0

    try:
        query_vector = embed_query(args.query, model=args.model, project_root=PROJECT_ROOT)
        points = search_qdrant(
            client=client,
            collection=args.collection,
            query_vector=query_vector,
            top_k=args.top_k,
        )
        results = build_context_items(points)
        content = render_context(args.query, results, args.top_k, args.format)
        if args.out is not None:
            write_text_output(args.out, content, overwrite=args.overwrite)
            summary["written"] = str(args.out)
            summary["results_count"] = len(results)
            print_summary(summary)
        else:
            print(content, end="")
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
