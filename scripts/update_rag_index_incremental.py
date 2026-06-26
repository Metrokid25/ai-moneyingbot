"""Incrementally update the RAG vector index from the Archive Bot DB.

Read-only consumer of archive.db. Detects chunks that are not yet indexed
(against a manifest), embeds ONLY the new chunks with Voyage, and upserts them
into the existing Qdrant collection without recreating it. Existing points are
preserved (point ids are deterministic uuid5 of chunk_id, so re-runs are
idempotent). See docs/rag_ingest_boundary.md (read-only consumption) and
docs/rag_incremental_index_update.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (str(SCRIPTS_DIR), str(PROJECT_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import export_archive_articles as exporter
import ingest_archive_export as ingester
from rag_chunking import build_chunk_records
from rag_qdrant import (
    DEFAULT_COLLECTION,
    DEFAULT_QDRANT_PATH,
    DEFAULT_VECTOR_SIZE,
    QdrantClient,
    build_points,
    ensure_collection_for_load,
    load_ids,
    upsert_points,
)

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "archive.db"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "data" / "rag_index_manifest.jsonl"
DEFAULT_SEED_IDS_PATH = PROJECT_ROOT / "data" / "embeddings_phase2_ids.npy"
DEFAULT_EMBED_MODEL = "voyage-3-large"
DEFAULT_EMBED_BATCH = 128
DEFAULT_UPSERT_BATCH = 256


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def load_manifest(manifest_path: Path, seed_ids_path: Path | None = None) -> set[str]:
    """Return the set of chunk_ids already indexed.

    If the manifest does not exist yet, seed it from an existing embeddings ids
    .npy (the chunk_ids loaded into Qdrant by the last full build).
    """
    if manifest_path.exists():
        indexed: set[str] = set()
        with manifest_path.open("r", encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                cid = str(row.get("chunk_id", "")).strip()
                if cid:
                    indexed.add(cid)
        return indexed
    if seed_ids_path is not None and seed_ids_path.exists():
        return {str(cid) for cid in load_ids(seed_ids_path)}
    return set()


def append_manifest(manifest_path: Path, chunk_ids: list[str]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8", newline="\n") as fh:
        for cid in chunk_ids:
            fh.write(json.dumps({"chunk_id": cid}, ensure_ascii=False) + "\n")


def collect_current_chunks(db_path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    """Read archive.db (read-only) and build the full current chunk set in memory."""
    rows = exporter.fetch_rows(db_path, limit)
    records = [rec for rec in (exporter.build_export_record(r) for r in rows) if rec is not None]
    normalized, _stats = ingester.normalize_articles(records)
    chunks: list[dict[str, Any]] = []
    for article in normalized:
        chunks.extend(build_chunk_records(article))
    return chunks


def select_new_chunks(chunks: list[dict[str, Any]], indexed_ids: set[str]) -> list[dict[str, Any]]:
    return [c for c in chunks if str(c["chunk_id"]) not in indexed_ids]


def embed_new_chunks(
    chunks: list[dict[str, Any]],
    model: str = DEFAULT_EMBED_MODEL,
    batch_size: int = DEFAULT_EMBED_BATCH,
) -> np.ndarray:
    if not os.environ.get("VOYAGE_API_KEY"):
        raise RuntimeError("VOYAGE_API_KEY is required to embed new chunks")
    import voyageai

    client = voyageai.Client()
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        texts = [c["embedding_text"] for c in batch]
        result = client.embed(texts=texts, model=model, input_type="document")
        vectors.extend(result.embeddings)
    return np.asarray(vectors, dtype=np.float32)


def upsert_new_chunks(
    chunks: list[dict[str, Any]],
    embeddings: np.ndarray,
    qdrant_path: Path,
    collection: str,
    batch_size: int = DEFAULT_UPSERT_BATCH,
) -> int:
    if QdrantClient is None:
        raise RuntimeError("qdrant_client is required for upsert")
    ids = [str(c["chunk_id"]) for c in chunks]
    points = build_points(chunks, embeddings, ids)
    client = QdrantClient(path=str(qdrant_path))
    try:
        # Create the collection only if it does not exist yet; for incremental
        # updates the collection already exists and we upsert straight into it
        # (deterministic uuid5 point ids make re-runs idempotent).
        if not client.collection_exists(collection_name=collection):
            ensure_collection_for_load(
                client=client,
                collection_name=collection,
                vector_size=DEFAULT_VECTOR_SIZE,
                recreate=False,
                execute=True,
            )
        return upsert_points(
            client=client,
            collection_name=collection,
            points=points,
            batch_size=batch_size,
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Incrementally update the RAG Qdrant index from archive.db (read-only).",
        epilog="Read-only on archive.db. Use --dry-run to detect new chunks without embedding/upserting.",
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--seed-ids-path", type=Path, default=DEFAULT_SEED_IDS_PATH)
    parser.add_argument("--qdrant-path", type=Path, default=PROJECT_ROOT / DEFAULT_QDRANT_PATH)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    parser.add_argument("--embed-batch-size", type=int, default=DEFAULT_EMBED_BATCH)
    parser.add_argument("--upsert-batch-size", type=int, default=DEFAULT_UPSERT_BATCH)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit how many archive articles are scanned (read window). Mainly for testing; "
        "leaving it set can leave later articles permanently unindexed.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    if args.dry_run and args.execute:
        print("[ERROR] --dry-run and --execute are mutually exclusive.", file=sys.stderr)
        return 2
    if not args.dry_run and not args.execute:
        print(
            "[ERROR] Refusing to embed/upsert. Use --dry-run to detect new chunks "
            "or --execute to embed and upsert them.",
            file=sys.stderr,
        )
        return 2
    if not args.db_path.exists():
        print(f"[ERROR] archive db not found: {args.db_path}", file=sys.stderr)
        return 1

    try:
        indexed_ids = load_manifest(args.manifest_path, args.seed_ids_path)
        chunks = collect_current_chunks(args.db_path, args.limit)
    except Exception as exc:  # noqa: BLE001 - report cleanly
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    new_chunks = select_new_chunks(chunks, indexed_ids)

    summary: dict[str, Any] = {
        "db_path": str(args.db_path),
        "qdrant_path": str(args.qdrant_path),
        "collection": args.collection,
        "manifest_path": str(args.manifest_path),
        "indexed_chunks": len(indexed_ids),
        "current_chunks": len(chunks),
        "new_chunks": len(new_chunks),
        "dry_run": bool(args.dry_run),
        "execute": bool(args.execute),
    }

    if args.dry_run or not new_chunks:
        if args.execute and not new_chunks:
            summary["note"] = "index already current; nothing to embed or upsert"
        else:
            summary["note"] = "dry-run: detected new chunks only; no embedding/upsert performed"
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    try:
        embeddings = embed_new_chunks(new_chunks, args.embed_model, args.embed_batch_size)
        written_batches = upsert_new_chunks(
            new_chunks, embeddings, args.qdrant_path, args.collection, args.upsert_batch_size
        )
        append_manifest(args.manifest_path, [str(c["chunk_id"]) for c in new_chunks])
    except Exception as exc:  # noqa: BLE001 - report cleanly
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    summary["embedded_new"] = len(new_chunks)
    summary["upserted_points"] = len(new_chunks)
    summary["upserted_batches"] = written_batches
    summary["note"] = "embedded new chunks and upserted into Qdrant; manifest updated"
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
