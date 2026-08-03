"""Inspect dense and rerank candidates for selected RAG gold questions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path.cwd()
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rag_retrieval import (  # noqa: E402
    DEFAULT_MODEL,
    embed_query,
    extract_source_metadata,
    make_snippet,
    open_qdrant_client,
)
from rag_retrieve_rerank import make_qdrant_search_fn, retrieve_then_rerank  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def chunk_id_of(row: dict[str, Any]) -> str | None:
    value = row.get("chunk_id")
    return str(value) if value is not None else None


def rank_of(expected: set[str], rows: list[dict[str, Any]]) -> int | None:
    for index, row in enumerate(rows, start=1):
        if chunk_id_of(row) in expected:
            return index
    return None


def dense_row(point: Any, rank: int) -> dict[str, Any]:
    payload = getattr(point, "payload", None) or {}
    return {
        "rank": rank,
        "dense_score": float(getattr(point, "score", 0.0)),
        **extract_source_metadata(payload),
        "snippet": make_snippet(payload.get("text")),
    }


def rerank_row(row: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "rerank_score": row.get("rerank_score"),
        "dense_score": row.get("dense_score"),
        "chunk_id": row.get("chunk_id"),
        "article_id": row.get("article_id"),
        "title": row.get("title"),
        "posted_at": row.get("posted_at"),
        "snippet": make_snippet(row.get("text") or row.get("snippet")),
    }


def diagnose(
    *,
    gold_rows: list[dict[str, Any]],
    selected_ids: set[str],
    qdrant_path: Path,
    collection: str,
    model: str,
    fetch_k: int,
    top_k: int,
) -> list[dict[str, Any]]:
    selected = [row for row in gold_rows if row["id"] in selected_ids]
    missing_ids = selected_ids - {row["id"] for row in selected}
    if missing_ids:
        raise ValueError(f"unknown gold id(s): {', '.join(sorted(missing_ids))}")

    client = open_qdrant_client(qdrant_path)
    search_fn = make_qdrant_search_fn(client, collection)
    records: list[dict[str, Any]] = []
    try:
        for gold in selected:
            vector = embed_query(gold["question"], model=model, project_root=PROJECT_ROOT)
            points = list(search_fn(vector, fetch_k))[:fetch_k]
            dense = [dense_row(point, index) for index, point in enumerate(points, start=1)]
            reranked_raw = retrieve_then_rerank(
                gold["question"],
                vector,
                search_fn=search_fn,
                fetch_k=fetch_k,
                top_k=top_k,
            )
            reranked = [rerank_row(row, index) for index, row in enumerate(reranked_raw, start=1)]
            expected = {str(value) for value in gold["expected_chunk_ids"]}
            records.append(
                {
                    "id": gold["id"],
                    "rule_id": gold.get("rule_id"),
                    "question": gold["question"],
                    "expected_chunk_ids": sorted(expected),
                    "dense_rank_within_fetch_k": rank_of(expected, dense),
                    "rerank_rank_within_top_k": rank_of(expected, reranked),
                    "dense_top": dense[:top_k],
                    "rerank_top": reranked,
                }
            )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--id", action="append", required=True, dest="ids")
    parser.add_argument("--qdrant-path", type=Path, default=Path("data/qdrant"))
    parser.add_argument("--collection", default="goodmorning_chunks")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--fetch-k", type=int, default=50)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = diagnose(
        gold_rows=read_jsonl(args.gold.resolve()),
        selected_ids=set(args.ids),
        qdrant_path=args.qdrant_path.resolve(),
        collection=args.collection,
        model=args.model,
        fetch_k=args.fetch_k,
        top_k=args.top_k,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in records:
        print(
            f"{row['id']}: dense_fetch_rank={row['dense_rank_within_fetch_k']} "
            f"rerank_top_rank={row['rerank_rank_within_top_k']}"
        )
    print(f"report={args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
