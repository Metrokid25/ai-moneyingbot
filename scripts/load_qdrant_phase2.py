import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from qdrant_client import QdrantClient

from rag_qdrant import (
    DEFAULT_COLLECTION,
    DEFAULT_QDRANT_PATH,
    DEFAULT_VECTOR_SIZE,
    build_points,
    ensure_collection_for_load,
    load_chunks_jsonl,
    load_embeddings,
    load_ids,
    summarize_inputs,
    upsert_points,
    validate_qdrant_inputs,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHUNKS_PATH = PROJECT_ROOT / "data" / "chunks_phase2.jsonl"
DEFAULT_EMBEDDINGS_PATH = PROJECT_ROOT / "data" / "embeddings_phase2.npy"
DEFAULT_IDS_PATH = PROJECT_ROOT / "data" / "embeddings_phase2_ids.npy"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load Phase 2 chunk embeddings into Qdrant")
    parser.add_argument("--chunks-path", type=Path, default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--embeddings-path", type=Path, default=DEFAULT_EMBEDDINGS_PATH)
    parser.add_argument("--ids-path", type=Path, default=DEFAULT_IDS_PATH)
    parser.add_argument("--qdrant-path", type=Path, default=PROJECT_ROOT / DEFAULT_QDRANT_PATH)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--recreate", action="store_true")
    return parser.parse_args()


def limited_inputs(
    chunks: list[dict[str, Any]],
    embeddings,
    ids,
    limit: int | None,
) -> tuple[list[dict[str, Any]], Any, list[str]]:
    if limit is None:
        id_strings = [str(chunk_id) for chunk_id in ids]
        return chunks, embeddings, id_strings
    if limit < 0:
        raise ValueError("--limit must be non-negative")

    limited_ids = [str(chunk_id) for chunk_id in ids[:limit]]
    chunk_by_id = {str(chunk.get("chunk_id", "")): chunk for chunk in chunks}
    limited_chunks = []
    for chunk_id in limited_ids:
        chunk = chunk_by_id.get(chunk_id)
        if chunk is None:
            raise ValueError(f"id {chunk_id} not found in chunks")
        limited_chunks.append(chunk)
    return limited_chunks, embeddings[:limit], limited_ids


def print_summary(summary: dict[str, Any]) -> None:
    print("=== Phase 2 Qdrant load summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")


def main() -> int:
    args = parse_args()
    if args.batch_size <= 0:
        print("[ERROR] --batch-size must be positive", file=sys.stderr)
        return 2
    if args.dry_run and args.execute:
        print("[ERROR] --dry-run and --execute are mutually exclusive.", file=sys.stderr)
        return 1
    if args.recreate and not args.execute:
        print("[ERROR] --recreate requires --execute", file=sys.stderr)
        return 2
    if not args.dry_run and not args.execute:
        print(
            "[ERROR] Refusing to create or upsert Qdrant data. "
            "Use --dry-run for validation or --execute for real loading.",
            file=sys.stderr,
        )
        return 2

    try:
        chunks = load_chunks_jsonl(args.chunks_path)
        embeddings = load_embeddings(args.embeddings_path)
        ids = load_ids(args.ids_path)
        selected_chunks, selected_embeddings, selected_ids = limited_inputs(
            chunks,
            embeddings,
            ids,
            args.limit,
        )
        validate_qdrant_inputs(
            selected_chunks,
            selected_embeddings,
            selected_ids,
            vector_size=DEFAULT_VECTOR_SIZE,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    selected_count = len(selected_chunks)
    batch_count = (selected_count + args.batch_size - 1) // args.batch_size if selected_count else 0
    summary = summarize_inputs(selected_chunks, selected_embeddings, selected_ids)
    summary.update(
        {
            "collection": args.collection,
            "qdrant_path": str(args.qdrant_path),
            "batch_size": args.batch_size,
            "batch_count": batch_count,
            "dry_run": bool(args.dry_run),
            "execute": bool(args.execute),
            "recreate": bool(args.recreate),
        }
    )

    if args.dry_run:
        print_summary(summary)
        return 0

    try:
        points = build_points(selected_chunks, selected_embeddings, selected_ids)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    client = QdrantClient(path=str(args.qdrant_path))
    try:
        ensure_collection_for_load(
            client=client,
            collection_name=args.collection,
            vector_size=DEFAULT_VECTOR_SIZE,
            recreate=args.recreate,
            execute=args.execute,
        )
        written_batches = upsert_points(
            client=client,
            collection_name=args.collection,
            points=points,
            batch_size=args.batch_size,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    summary["written_points"] = len(points)
    summary["written_batches"] = written_batches
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
