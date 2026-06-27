import sys

import pytest

sys.path.insert(0, "src")

import rag_rerank


def _candidates():
    # rank from dense retrieval is deliberately "wrong" so reranking must reorder it
    return [
        {"rank": 1, "chunk_id": "a", "article_id": 1, "score": 0.9, "text": "short"},
        {"rank": 2, "chunk_id": "b", "article_id": 2, "score": 0.8, "text": "medium length"},
        {"rank": 3, "chunk_id": "c", "article_id": 3, "score": 0.7, "text": "the longest document here"},
    ]


def _fake_by_length(query, documents, top_k):
    # pretend the longest document is most relevant; return best-first, capped at top_k
    order = sorted(range(len(documents)), key=lambda i: -len(documents[i]))
    return [(i, float(len(documents[i]))) for i in order[:top_k]]


def test_reorders_truncates_and_renumbers():
    out = rag_rerank.rerank_candidates(
        "q", _candidates(), top_k=2, rerank_fn=_fake_by_length
    )

    assert [c["chunk_id"] for c in out] == ["c", "b"]  # longest first
    assert [c["rank"] for c in out] == [1, 2]  # renumbered
    assert out[0]["rerank_score"] == float(len("the longest document here"))
    # original metadata preserved
    assert out[0]["article_id"] == 3


def test_does_not_mutate_input():
    candidates = _candidates()
    snapshot = [dict(c) for c in candidates]

    rag_rerank.rerank_candidates("q", candidates, top_k=3, rerank_fn=_fake_by_length)

    assert candidates == snapshot  # caller's dicts untouched (rank/score not added)


def test_top_k_larger_than_candidates_returns_all():
    out = rag_rerank.rerank_candidates(
        "q", _candidates(), top_k=10, rerank_fn=_fake_by_length
    )
    assert len(out) == 3
    assert [c["rank"] for c in out] == [1, 2, 3]


def test_empty_candidates_returns_empty():
    called = False

    def fn(query, documents, top_k):
        nonlocal called
        called = True
        return []

    out = rag_rerank.rerank_candidates("q", [], top_k=5, rerank_fn=fn)
    assert out == []
    assert called is False  # short-circuits before calling the reranker


def test_empty_query_rejected():
    with pytest.raises(ValueError):
        rag_rerank.rerank_candidates("   ", _candidates(), top_k=2, rerank_fn=_fake_by_length)


def test_non_positive_top_k_rejected():
    with pytest.raises(ValueError):
        rag_rerank.rerank_candidates("q", _candidates(), top_k=0, rerank_fn=_fake_by_length)


def test_missing_or_empty_text_rejected():
    bad = [{"chunk_id": "a", "text": ""}, {"chunk_id": "b", "text": "ok"}]
    with pytest.raises(ValueError):
        rag_rerank.rerank_candidates("q", bad, top_k=1, rerank_fn=_fake_by_length)

    missing = [{"chunk_id": "a"}]
    with pytest.raises(ValueError):
        rag_rerank.rerank_candidates("q", missing, top_k=1, rerank_fn=_fake_by_length)


def test_out_of_range_index_from_reranker_rejected():
    def fn(query, documents, top_k):
        return [(99, 1.0)]

    with pytest.raises(ValueError):
        rag_rerank.rerank_candidates("q", _candidates(), top_k=1, rerank_fn=fn)


def test_duplicate_index_from_reranker_rejected():
    def fn(query, documents, top_k):
        return [(0, 1.0), (0, 0.9)]

    with pytest.raises(ValueError):
        rag_rerank.rerank_candidates("q", _candidates(), top_k=2, rerank_fn=fn)


def test_custom_text_and_score_keys():
    candidates = [
        {"chunk_id": "a", "body": "alpha"},
        {"chunk_id": "b", "body": "beta beta"},
    ]

    def fn(query, documents, top_k):
        # documents must have been read from the custom text_key ("body")
        assert documents == ["alpha", "beta beta"]
        return [(1, 0.5), (0, 0.1)]

    out = rag_rerank.rerank_candidates(
        "q", candidates, top_k=2, rerank_fn=fn, text_key="body", score_key="relevance"
    )
    assert [c["chunk_id"] for c in out] == ["b", "a"]
    assert out[0]["relevance"] == 0.5


def test_too_many_candidates_rejected():
    big = [{"text": "x"} for _ in range(rag_rerank.MAX_CANDIDATES + 1)]
    with pytest.raises(ValueError):
        rag_rerank.rerank_candidates("q", big, top_k=5, rerank_fn=_fake_by_length)
