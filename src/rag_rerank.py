"""src/rag_rerank.py — Voyage reranking over dense-retrieval candidates.

Dense retrieval (voyage-3-large + Qdrant) fails to put the ground-truth chunk in
the top-10 for ~half of the phase-1 eval queries; several land at rank 11-100,
i.e. retrieval found the right chunk but ranked it poorly. A cross-encoder
reranker re-scores (query, full-chunk-text) pairs and recovers those cases.

This module is intentionally split so it is unit-testable without network/DB:
- `rerank_candidates(...)` holds the pure reorder/truncate/renumber/score logic
  and takes an injectable `rerank_fn`.
- `_voyage_rerank_fn(...)` is the only place that calls the Voyage API.

Candidates are plain dicts (e.g. rows from rag_retrieval.format_search_results,
but carrying the FULL chunk text under `text_key`, not just a snippet). The
returned list is a reordered copy of the inputs with `rerank_score` added and
`rank` renumbered 1..N; inputs are not mutated.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Sequence

DEFAULT_RERANK_MODEL = "rerank-2"
DEFAULT_TEXT_KEY = "text"
DEFAULT_SCORE_KEY = "rerank_score"
MAX_CANDIDATES = 1000

# A rerank function takes (query, documents, top_k) and returns
# (candidate_index, relevance_score) pairs ALREADY ordered best-first.
RerankFn = Callable[[str, list[str], int], list[tuple[int, float]]]


def rerank_candidates(
    query: str,
    candidates: Sequence[dict[str, Any]],
    *,
    top_k: int,
    rerank_fn: RerankFn | None = None,
    text_key: str = DEFAULT_TEXT_KEY,
    score_key: str = DEFAULT_SCORE_KEY,
    model: str = DEFAULT_RERANK_MODEL,
    project_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Rerank `candidates` for `query` and return the top_k reordered copies.

    `rerank_fn` defaults to the real Voyage reranker; inject a fake in tests.
    Raises ValueError on bad input or on a reranker that returns an
    out-of-range / duplicate index.
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1 (got {top_k})")

    candidates = list(candidates)
    if not candidates:
        return []
    if len(candidates) > MAX_CANDIDATES:
        raise ValueError(f"too many candidates: {len(candidates)} > {MAX_CANDIDATES}")

    documents: list[str] = []
    for i, candidate in enumerate(candidates):
        text = candidate.get(text_key)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"candidate {i} has empty {text_key!r}")
        documents.append(text)

    fn = rerank_fn or _voyage_rerank_fn(model=model, project_root=project_root)
    ranking = fn(query, documents, top_k)

    reranked: list[dict[str, Any]] = []
    seen: set[int] = set()
    for new_rank, (idx, score) in enumerate(ranking, start=1):
        if not 0 <= idx < len(candidates):
            raise ValueError(f"rerank returned out-of-range index {idx}")
        if idx in seen:
            raise ValueError(f"rerank returned duplicate index {idx}")
        seen.add(idx)

        item = dict(candidates[idx])  # copy — never mutate the caller's dicts
        item[score_key] = float(score)
        item["rank"] = new_rank
        reranked.append(item)
        if len(reranked) >= top_k:
            break

    return reranked


def _load_voyage_api_key(project_root: Path | None = None) -> str:
    from dotenv import load_dotenv

    if project_root is not None:
        load_dotenv(project_root / ".env")
    else:
        load_dotenv()
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY is required for reranking")
    return api_key


def _voyage_rerank_fn(
    *,
    model: str = DEFAULT_RERANK_MODEL,
    project_root: Path | None = None,
) -> RerankFn:
    """Build the real Voyage reranker. Imports voyageai lazily so this module
    stays importable (and unit-testable) without the SDK present."""

    def fn(query: str, documents: list[str], top_k: int) -> list[tuple[int, float]]:
        _load_voyage_api_key(project_root)

        import voyageai

        client = voyageai.Client()
        result = client.rerank(
            query=query,
            documents=documents,
            model=model,
            top_k=top_k,
        )
        return [(item.index, float(item.relevance_score)) for item in result.results]

    return fn
