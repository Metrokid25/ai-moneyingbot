"""src/rag_retrieve_rerank.py — dense retrieve → rerank pipeline.

Dense retrieval alone leaves ~half of the phase-1 eval queries with the
ground-truth chunk outside top-10 (several at rank 11-100). This pipeline
over-fetches `fetch_k` candidates by vector similarity, then reranks them with
`rag_rerank` (Voyage rerank-2) to keep the best `top_k` — recovering the
mis-ranked-but-retrieved chunks.

Both sides are injectable so the pipeline logic is unit-tested without the
Qdrant index or the Voyage API:
- `search_fn(query_vector, fetch_k) -> points` (default: Qdrant, see
  `make_qdrant_search_fn`)
- `rerank_fn` (forwarded to rag_rerank; default: Voyage)

A "point" is anything with `.payload` (a dict containing the full chunk text
under "text") and `.score` — i.e. a qdrant_client search hit.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Sequence

import rag_rerank
from rag_retrieval import (
    ensure_collection_exists,
    extract_source_metadata,
    make_snippet,
    validate_query_vector,
)

DEFAULT_FETCH_K = 50
MAX_FETCH_K = 200

_LOGGER = logging.getLogger(__name__)

# (query_vector, fetch_k) -> list of qdrant-like points
SearchFn = Callable[[Sequence[float], int], list[Any]]


def _candidate_from_point(point: Any, *, text_key: str = rag_rerank.DEFAULT_TEXT_KEY) -> dict[str, Any]:
    """Build a rerank candidate from a Qdrant point, carrying the FULL chunk
    text (from payload["text"]) plus the dense score, source metadata, and a
    snippet for display."""
    payload = getattr(point, "payload", None) or {}
    text = payload.get("text")
    return {
        "dense_score": getattr(point, "score", None),
        **extract_source_metadata(payload),
        text_key: text,
        "snippet": make_snippet(text),
    }


def retrieve_then_rerank(
    query_text: str,
    query_vector: Sequence[float],
    *,
    search_fn: SearchFn,
    top_k: int,
    fetch_k: int = DEFAULT_FETCH_K,
    rerank_fn: rag_rerank.RerankFn | None = None,
    text_key: str = rag_rerank.DEFAULT_TEXT_KEY,
) -> list[dict[str, Any]]:
    """Over-fetch `fetch_k` candidates via `search_fn`, rerank, return top_k.

    Candidates whose chunk text is missing/empty are dropped before reranking
    (they cannot be scored by a text reranker). Returns [] if nothing rerankable
    came back. Raises ValueError on bad bounds or an empty query.
    """
    if not query_text or not query_text.strip():
        raise ValueError("query_text must not be empty")
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1 (got {top_k})")
    if not 1 <= fetch_k <= MAX_FETCH_K:
        raise ValueError(f"fetch_k must be between 1 and {MAX_FETCH_K} (got {fetch_k})")
    if top_k > fetch_k:
        raise ValueError(f"top_k ({top_k}) must be <= fetch_k ({fetch_k})")
    validate_query_vector(query_vector)

    # fetch_k is only a *request* to search_fn; enforce it here so the candidate
    # count is actually bounded regardless of what search_fn returns.
    points = list(search_fn(query_vector, fetch_k))[:fetch_k]
    candidates = [_candidate_from_point(point, text_key=text_key) for point in points]
    rerankable = [
        candidate
        for candidate in candidates
        if isinstance(candidate.get(text_key), str) and candidate[text_key].strip()
    ]
    dropped = len(candidates) - len(rerankable)
    if dropped:
        # empty chunk text usually means an index/payload problem — don't shrink
        # the pool below top_k silently.
        _LOGGER.warning(
            "retrieve_then_rerank: dropped %d/%d candidate(s) with empty %r before reranking",
            dropped,
            len(candidates),
            text_key,
        )
    if not rerankable:
        return []

    return rag_rerank.rerank_candidates(
        query_text,
        rerankable,
        top_k=top_k,
        rerank_fn=rerank_fn,
        text_key=text_key,
    )


def make_qdrant_search_fn(client: Any, collection: str) -> SearchFn:
    """Build the real Qdrant search_fn. Unlike rag_retrieval.search_qdrant (capped
    at MAX_TOP_K=20), this allows the larger `fetch_k` over-fetch reranking needs.

    Note: this intentionally does NOT apply a score_threshold (unlike search_qdrant) —
    over-fetching the low-similarity tail is the whole point, since rerank is what
    rescues those. Add filtering downstream if needed.
    """

    def search_fn(query_vector: Sequence[float], fetch_k: int) -> list[Any]:
        vector = validate_query_vector(query_vector)
        ensure_collection_exists(client, collection)
        return list(
            client.search(
                collection_name=collection,
                query_vector=vector.tolist(),
                limit=fetch_k,
                with_payload=True,
                with_vectors=False,
            )
        )

    return search_fn
