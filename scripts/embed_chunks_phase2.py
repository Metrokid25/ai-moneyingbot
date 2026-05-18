import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHUNKS_PATH = PROJECT_ROOT / "data" / "chunks_phase2.jsonl"
DEFAULT_OUT_EMBEDDINGS = PROJECT_ROOT / "data" / "embeddings_phase2.npy"
DEFAULT_OUT_IDS = PROJECT_ROOT / "data" / "embeddings_phase2_ids.npy"
DEFAULT_PROGRESS_PATH = PROJECT_ROOT / "data" / "embeddings_phase2_progress.jsonl"
DEFAULT_MOCK_OUT_EMBEDDINGS = PROJECT_ROOT / "data" / "embeddings_phase2_mock.npy"
DEFAULT_MOCK_OUT_IDS = PROJECT_ROOT / "data" / "embeddings_phase2_mock_ids.npy"
DEFAULT_MOCK_PROGRESS_PATH = PROJECT_ROOT / "data" / "embeddings_phase2_mock_progress.jsonl"

DEFAULT_MODEL = "voyage-3-large"
DEFAULT_BATCH_SIZE = 128
VECTOR_SIZE = 1024


def read_chunks(chunks_path: Path) -> tuple[list[dict[str, str]], dict[str, int]]:
    chunks: list[dict[str, str]] = []
    bad_json_count = 0
    empty_embedding_text_count = 0

    with chunks_path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad_json_count += 1
                continue

            chunk_id = obj.get("chunk_id")
            embedding_text = obj.get("embedding_text")
            if chunk_id is None:
                chunk_id = ""
            if embedding_text is None:
                embedding_text = ""
            if not str(embedding_text).strip():
                empty_embedding_text_count += 1
            chunks.append(
                {
                    "chunk_id": str(chunk_id),
                    "embedding_text": str(embedding_text),
                }
            )

    seen: set[str] = set()
    duplicate_chunk_ids = 0
    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        if chunk_id in seen:
            duplicate_chunk_ids += 1
        else:
            seen.add(chunk_id)

    stats = {
        "bad_json_count": bad_json_count,
        "duplicate_chunk_ids": duplicate_chunk_ids,
        "empty_embedding_text_count": empty_embedding_text_count,
    }
    return chunks, stats


def read_done_chunk_ids(progress_path: Path) -> set[str]:
    if not progress_path.exists():
        return set()

    done: set[str] = set()
    with progress_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("status") == "OK" and obj.get("chunk_id"):
                done.add(str(obj["chunk_id"]))
    return done


def select_chunks(
    chunks: list[dict[str, str]],
    limit: int | None,
    resume: bool,
    done_chunk_ids: set[str],
) -> tuple[list[dict[str, str]], int]:
    selected = chunks[:limit] if limit is not None else chunks
    already_done_count = 0
    if resume:
        remaining = []
        for chunk in selected:
            if chunk["chunk_id"] in done_chunk_ids:
                already_done_count += 1
            else:
                remaining.append(chunk)
        return remaining, already_done_count
    return selected, 0


def mock_embedding(chunk_id: str, vector_size: int = VECTOR_SIZE) -> np.ndarray:
    digest = hashlib.sha256(chunk_id.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], byteorder="little", signed=False)
    rng = np.random.default_rng(seed)
    return rng.random(vector_size, dtype=np.float32)


def build_mock_embeddings(chunks: list[dict[str, str]]) -> tuple[np.ndarray, np.ndarray]:
    embeddings = np.vstack([mock_embedding(chunk["chunk_id"]) for chunk in chunks]).astype(np.float32)
    ids = np.array([chunk["chunk_id"] for chunk in chunks], dtype=str)
    return embeddings, ids


def write_mock_outputs(
    chunks: list[dict[str, str]],
    out_embeddings: Path,
    out_ids: Path,
    progress_path: Path,
    model: str,
    overwrite: bool,
) -> tuple[tuple[int, ...], int]:
    for path in (out_embeddings, out_ids, progress_path):
        if path.exists() and not overwrite:
            raise FileExistsError(f"{path} already exists; pass --overwrite")

    out_embeddings.parent.mkdir(parents=True, exist_ok=True)
    out_ids.parent.mkdir(parents=True, exist_ok=True)
    progress_path.parent.mkdir(parents=True, exist_ok=True)

    if chunks:
        embeddings, ids = build_mock_embeddings(chunks)
    else:
        embeddings = np.empty((0, VECTOR_SIZE), dtype=np.float32)
        ids = np.array([], dtype=str)

    np.save(out_embeddings, embeddings)
    np.save(out_ids, ids)
    with progress_path.open("w", encoding="utf-8", newline="\n") as fh:
        for index, chunk in enumerate(chunks):
            record = {
                "chunk_id": chunk["chunk_id"],
                "index": index,
                "status": "OK",
                "model": model,
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return embeddings.shape, len(ids)


def embed_with_voyage_execute(
    chunks: list[dict[str, str]],
    out_embeddings: Path,
    out_ids: Path,
    progress_path: Path,
    model: str,
    batch_size: int,
    overwrite: bool,
) -> tuple[tuple[int, ...], int]:
    if not os.environ.get("VOYAGE_API_KEY"):
        raise RuntimeError("VOYAGE_API_KEY is required for --execute")
    for path in (out_embeddings, out_ids, progress_path):
        if path.exists() and not overwrite:
            raise FileExistsError(f"{path} already exists; pass --overwrite")

    import voyageai

    client = voyageai.Client()
    all_embeddings: list[list[float]] = []
    all_ids: list[str] = []

    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with progress_path.open("w", encoding="utf-8", newline="\n") as progress_fh:
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            texts = [chunk["embedding_text"] for chunk in batch]
            result = client.embed(texts=texts, model=model, input_type="document")
            all_embeddings.extend(result.embeddings)
            for offset, chunk in enumerate(batch):
                index = start + offset
                all_ids.append(chunk["chunk_id"])
                progress_fh.write(
                    json.dumps(
                        {
                            "chunk_id": chunk["chunk_id"],
                            "index": index,
                            "status": "OK",
                            "model": model,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            time.sleep(0.1)

    embeddings = np.array(all_embeddings, dtype=np.float32)
    ids = np.array(all_ids, dtype=str)
    np.save(out_embeddings, embeddings)
    np.save(out_ids, ids)
    return embeddings.shape, len(ids)


def resolve_output_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    out_embeddings = args.out_embeddings
    out_ids = args.out_ids
    progress_path = args.progress_path
    if args.mock:
        if out_embeddings == DEFAULT_OUT_EMBEDDINGS:
            out_embeddings = DEFAULT_MOCK_OUT_EMBEDDINGS
        if out_ids == DEFAULT_OUT_IDS:
            out_ids = DEFAULT_MOCK_OUT_IDS
        if progress_path == DEFAULT_PROGRESS_PATH:
            progress_path = DEFAULT_MOCK_PROGRESS_PATH
    return out_embeddings, out_ids, progress_path


def build_summary(
    args: argparse.Namespace,
    chunks_path: Path,
    out_embeddings: Path,
    out_ids: Path,
    progress_path: Path,
    total_chunks: int,
    selected_chunks: int,
    stats: dict[str, int],
    already_done_count: int,
) -> dict[str, Any]:
    return {
        "chunks_path": str(chunks_path),
        "total_chunks": total_chunks,
        "selected_chunks": selected_chunks,
        "batch_size": args.batch_size,
        "model": args.model,
        "vector_size": VECTOR_SIZE,
        "bad_json_count": stats["bad_json_count"],
        "duplicate_chunk_ids": stats["duplicate_chunk_ids"],
        "empty_embedding_text_count": stats["empty_embedding_text_count"],
        "resume": bool(args.resume),
        "already_done_count": already_done_count,
        "remaining_count": selected_chunks,
        "output_embeddings": str(out_embeddings),
        "output_ids": str(out_ids),
        "progress_path": str(progress_path),
        "dry_run": bool(args.dry_run),
        "mock": bool(args.mock),
        "execute": bool(args.execute),
    }


def print_summary(summary: dict[str, Any]) -> None:
    print("=== Phase 2 chunk embedding summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare or build Phase 2 chunk embeddings")
    parser.add_argument("--chunks-path", type=Path, default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--out-embeddings", type=Path, default=DEFAULT_OUT_EMBEDDINGS)
    parser.add_argument("--out-ids", type=Path, default=DEFAULT_OUT_IDS)
    parser.add_argument("--progress-path", type=Path, default=DEFAULT_PROGRESS_PATH)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 0:
        print("[ERROR] --limit must be non-negative", file=sys.stderr)
        return 2
    if args.batch_size <= 0:
        print("[ERROR] --batch-size must be positive", file=sys.stderr)
        return 2
    if args.execute and (args.dry_run or args.mock):
        print("[ERROR] --execute cannot be combined with --dry-run or --mock", file=sys.stderr)
        return 2
    if not args.dry_run and not args.mock and not args.execute:
        print(
            "[ERROR] Refusing to call Voyage API. Use --dry-run for validation, "
            "--mock for fake vectors, or --execute for real API calls.",
            file=sys.stderr,
        )
        return 2

    out_embeddings, out_ids, progress_path = resolve_output_paths(args)
    chunks, stats = read_chunks(args.chunks_path)
    done_chunk_ids = read_done_chunk_ids(progress_path) if args.resume else set()
    selected_chunks, already_done_count = select_chunks(
        chunks,
        limit=args.limit,
        resume=args.resume,
        done_chunk_ids=done_chunk_ids,
    )

    summary = build_summary(
        args=args,
        chunks_path=args.chunks_path,
        out_embeddings=out_embeddings,
        out_ids=out_ids,
        progress_path=progress_path,
        total_chunks=len(chunks),
        selected_chunks=len(selected_chunks),
        stats=stats,
        already_done_count=already_done_count,
    )

    if args.dry_run:
        print_summary(summary)
        return 0

    try:
        if args.mock:
            shape, ids_count = write_mock_outputs(
                chunks=selected_chunks,
                out_embeddings=out_embeddings,
                out_ids=out_ids,
                progress_path=progress_path,
                model=args.model,
                overwrite=args.overwrite,
            )
        else:
            print("[WARN] --execute will call Voyage API and may incur cost.", file=sys.stderr)
            shape, ids_count = embed_with_voyage_execute(
                chunks=selected_chunks,
                out_embeddings=out_embeddings,
                out_ids=out_ids,
                progress_path=progress_path,
                model=args.model,
                batch_size=args.batch_size,
                overwrite=args.overwrite,
            )
    except FileExistsError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    summary["written_embedding_shape"] = shape
    summary["written_ids_count"] = ids_count
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
