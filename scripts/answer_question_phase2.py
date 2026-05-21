import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_answer_context import build_context_items
from rag_answering import (
    DEFAULT_ANSWER_MODEL,
    build_answer_messages,
    build_answer_record,
    build_sources,
    call_llm,
    format_answer_json,
    format_answer_markdown,
    format_context_for_prompt,
)
from rag_retrieval import (
    DEFAULT_COLLECTION,
    DEFAULT_MODEL,
    DEFAULT_QDRANT_PATH,
    DEFAULT_TOP_K,
    embed_query,
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a minimal Phase 2 RAG answer")
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--model", default=DEFAULT_ANSWER_MODEL)
    parser.add_argument("--embedding-model", default=DEFAULT_MODEL)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--qdrant-path", type=Path, default=PROJECT_ROOT / DEFAULT_QDRANT_PATH)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


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


def print_summary(summary: dict[str, Any]) -> None:
    print("=== Phase 2 RAG answer summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")


def render_answer(record: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return format_answer_json(record)
    return format_answer_markdown(record)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    try:
        ensure_query(args.query)
        validate_top_k(args.top_k)
        validate_run_mode(dry_run=args.dry_run, execute=args.execute)
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
        "answer_model": args.model,
        "embedding_model": args.embedding_model,
        "qdrant_path": str(args.qdrant_path),
        "collection": args.collection,
        "dry_run": bool(args.dry_run),
        "execute": bool(args.execute),
        "voyage_api_call": bool(args.execute),
        "llm_api_call": bool(args.execute),
        "qdrant_operation": "read/search only",
    }
    summary.update(collection_summary)

    if args.dry_run:
        print_summary(summary)
        print("=== Execution plan ===")
        print("1. Validate query, top_k, Qdrant path, and collection status.")
        print("2. Embed the query with Voyage only when --execute is used.")
        print("3. Search Qdrant top_k with payloads and without vectors.")
        print("4. Build answer context from retrieved chunks.")
        print("5. Generate the final Korean answer with the LLM only when --execute is used.")
        return 0

    try:
        query_vector = embed_query(args.query, model=args.embedding_model, project_root=PROJECT_ROOT)
        points = search_qdrant(
            client=client,
            collection=args.collection,
            query_vector=query_vector,
            top_k=args.top_k,
        )
        context_items = build_context_items(points)
        context = format_context_for_prompt(context_items)
        messages = build_answer_messages(args.query, context)
        answer = call_llm(messages, model=args.model)
        sources = build_sources(context_items)
        record = build_answer_record(
            query=args.query,
            answer=answer,
            sources=sources,
            model=args.model,
            top_k=args.top_k,
        )
        print(render_answer(record, args.format), end="")
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
