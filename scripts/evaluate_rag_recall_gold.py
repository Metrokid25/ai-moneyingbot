"""Measure id-based retrieval quality on the corpus gold set.

For each gold question (tests/fixtures/rag_eval_questions_corpus.jsonl, which
carries the source chunk in expected_chunk_ids), embed the query with Voyage,
run dense retrieval against the qdrant index, and find the rank of the gold
chunk. Optionally also run retrieve_then_rerank and compare. Reports
recall@1/5/10 and MRR@10 for dense vs rerank.

This is read-only: it queries the index and writes a report file, nothing else.
It reuses the existing retrieval/rerank code (no reimplementation):
rag_retrieval.embed_query, rag_retrieve_rerank.make_qdrant_search_fn /
retrieve_then_rerank.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

from rag_retrieval import (  # noqa: E402
    DEFAULT_COLLECTION,
    DEFAULT_MODEL,
    embed_query,
    open_qdrant_client,
    payload_value,
)
from rag_retrieve_rerank import make_qdrant_search_fn, retrieve_then_rerank  # noqa: E402

DEFAULT_GOLD_PATH = PROJECT_ROOT / "tests" / "fixtures" / "rag_eval_questions_corpus.jsonl"
DEFAULT_QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant"
DEFAULT_DEPTH = 10
DEFAULT_FETCH_K = 50
RECALL_KS = (1, 5, 10)


def load_gold(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        chunk_ids = row.get("expected_chunk_ids") or []
        if not chunk_ids:
            raise ValueError(f"{row.get('id')}: expected_chunk_ids is empty")
        rows.append(row)
    if not rows:
        raise ValueError(f"no gold rows in {path}")
    return rows


def chunk_id_of(source: dict[str, Any]) -> str | None:
    """chunk_id from a qdrant payload or a rerank candidate, or None if absent.

    Returns None (not the string "None") when missing, so a payload that lost its
    chunk_id never spuriously matches a gold id and a schema drift stays visible.
    """
    value = payload_value(source, "chunk_id")
    return None if value is None else str(value)


def rank_of(gold_chunk_ids: set[str], ranked_chunk_ids: list[str | None]) -> int | None:
    """1-based rank of the first ranked id that is one of the gold ids, else None."""
    for i, chunk_id in enumerate(ranked_chunk_ids, start=1):
        if chunk_id is not None and chunk_id in gold_chunk_ids:
            return i
    return None


def reciprocal_rank(rank: int | None, cap: int) -> float:
    if rank is None or rank > cap:
        return 0.0
    return 1.0 / rank


def summarize(ranks: list[int | None], depth: int) -> dict[str, Any]:
    n = len(ranks)
    out: dict[str, Any] = {"n": n}
    for k in RECALL_KS:
        hits = sum(1 for r in ranks if r is not None and r <= k)
        out[f"recall@{k}"] = round(hits / n, 4) if n else 0.0
    mrr = sum(reciprocal_rank(r, depth) for r in ranks) / n if n else 0.0
    out[f"mrr@{depth}"] = round(mrr, 4)
    out["found"] = sum(1 for r in ranks if r is not None)
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD_PATH)
    parser.add_argument("--qdrant-path", type=Path, default=DEFAULT_QDRANT_PATH)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--embedding-model", default=DEFAULT_MODEL)
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH,
                        help="Rank depth scored for recall@10 / MRR@depth.")
    parser.add_argument("--fetch-k", type=int, default=DEFAULT_FETCH_K,
                        help="Over-fetch size for the rerank path.")
    parser.add_argument("--no-rerank", action="store_true", help="Dense baseline only (no Voyage rerank calls).")
    parser.add_argument("--limit", type=int, default=0, help="Only evaluate the first N questions (0 = all).")
    parser.add_argument("--out", type=Path, default=None, help="Report path (default: reports/rag_recall_gold_<ts>.json).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    gold = load_gold(args.gold)
    if args.limit:
        gold = gold[: args.limit]
    depth = max(args.depth, max(RECALL_KS))

    client = open_qdrant_client(args.qdrant_path)
    search_fn = make_qdrant_search_fn(client, args.collection)

    dense_ranks: list[int | None] = []
    rerank_ranks: list[int | None] = []
    per_question: list[dict[str, Any]] = []

    print(f"gold questions: {len(gold)} | depth: {depth} | fetch_k: {args.fetch_k} | "
          f"rerank: {'off' if args.no_rerank else 'on'}\n")
    print(f"{'id':<12} {'dense':>6} {'rerank':>7}  question")

    for row in gold:
        gold_chunks = {str(cid) for cid in row["expected_chunk_ids"]}
        question = row["question"]
        vector = embed_query(question, model=args.embedding_model, project_root=PROJECT_ROOT)

        dense_points = list(search_fn(vector, depth))
        dense_ids = [chunk_id_of(getattr(p, "payload", {}) or {}) for p in dense_points]
        d_rank = rank_of(gold_chunks, dense_ids)
        dense_ranks.append(d_rank)

        r_rank: int | None = None
        if not args.no_rerank:
            reranked = retrieve_then_rerank(
                question, vector, search_fn=search_fn, top_k=depth, fetch_k=args.fetch_k
            )
            rerank_ids = [chunk_id_of(c) for c in reranked]
            r_rank = rank_of(gold_chunks, rerank_ids)
            rerank_ranks.append(r_rank)

        per_question.append(
            {"id": row["id"], "gold_chunk_ids": sorted(gold_chunks), "dense_rank": d_rank, "rerank_rank": r_rank}
        )
        d_disp = str(d_rank) if d_rank is not None else "-"
        r_disp = ("-" if r_rank is None else str(r_rank)) if not args.no_rerank else "n/a"
        print(f"{row['id']:<12} {d_disp:>6} {r_disp:>7}  {question[:54]}")

    dense_summary = summarize(dense_ranks, depth)
    rerank_summary = summarize(rerank_ranks, depth) if not args.no_rerank else None

    print("\n=== summary ===")
    header = f"{'metric':<10} {'dense':>8}"
    if rerank_summary:
        header += f" {'rerank':>8} {'delta':>8}"
    print(header)
    for key in [f"recall@{k}" for k in RECALL_KS] + [f"mrr@{depth}"]:
        line = f"{key:<10} {dense_summary[key]:>8.4f}"
        if rerank_summary:
            delta = rerank_summary[key] - dense_summary[key]
            line += f" {rerank_summary[key]:>8.4f} {delta:>+8.4f}"
        print(line)
    print(f"{'found':<10} {dense_summary['found']:>8}" +
          (f" {rerank_summary['found']:>8}" if rerank_summary else ""))

    misses = [q["id"] for q in per_question if q["dense_rank"] is None]
    if misses:
        print(f"\ngold chunk never in top-{depth} (dense): {len(misses)} -> {', '.join(misses)}")

    out_path = args.out or (PROJECT_ROOT / "reports" /
                            f"rag_recall_gold_{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "gold_path": str(args.gold),
        "collection": args.collection,
        "embedding_model": args.embedding_model,
        "depth": depth,
        "fetch_k": args.fetch_k,
        "rerank": not args.no_rerank,
        "dense": dense_summary,
        "rerank_summary": rerank_summary,
        "per_question": per_question,
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
