import sys

import pytest

sys.path.insert(0, "src")

import rag_retrieve_rerank


QVEC = [0.1] * 1024  # valid 1024-dim query vector (rag_retrieval.validate_query_vector)


class FakePoint:
    def __init__(self, score, payload):
        self.score = score
        self.payload = payload


def _point(score, text, **meta):
    return FakePoint(score, {"text": text, **meta})


def _fake_by_length(query, documents, top_k):
    order = sorted(range(len(documents)), key=lambda i: -len(documents[i]))
    return [(i, float(len(documents[i]))) for i in order[:top_k]]


def test_over_fetch_then_rerank_returns_top_k():
    points = [
        _point(0.9, "short", article_id=1),
        _point(0.8, "medium length text", article_id=2),
        _point(0.7, "the longest candidate document here", article_id=3),
    ]
    seen_docs = {}

    def rerank_fn(query, documents, top_k):
        seen_docs["docs"] = list(documents)
        return _fake_by_length(query, documents, top_k)

    out = rag_retrieve_rerank.retrieve_then_rerank(
        "금리 인상",
        QVEC,
        search_fn=lambda vec, fetch_k: points,
        top_k=2,
        fetch_k=10,
        rerank_fn=rerank_fn,
    )

    assert [c["article_id"] for c in out] == [3, 2]  # reranked by length
    assert [c["rank"] for c in out] == [1, 2]
    # the reranker received FULL chunk text, not the 250-char snippet
    assert seen_docs["docs"] == ["short", "medium length text", "the longest candidate document here"]
    # dense score preserved for inspection
    assert out[0]["dense_score"] == 0.7


def test_drops_candidates_with_empty_text():
    points = [
        _point(0.9, "", article_id=1),  # empty text -> not rerankable
        _point(0.8, "real text", article_id=2),
    ]
    passed = {}

    def rerank_fn(query, documents, top_k):
        passed["docs"] = list(documents)
        return [(0, 1.0)]

    out = rag_retrieve_rerank.retrieve_then_rerank(
        "q", QVEC, search_fn=lambda vec, fetch_k: points, top_k=1, fetch_k=5, rerank_fn=rerank_fn
    )

    assert passed["docs"] == ["real text"]  # empty-text candidate filtered out
    assert [c["article_id"] for c in out] == [2]


def test_no_rerankable_candidates_returns_empty():
    points = [_point(0.9, ""), _point(0.8, "   ")]
    called = False

    def rerank_fn(query, documents, top_k):
        nonlocal called
        called = True
        return []

    out = rag_retrieve_rerank.retrieve_then_rerank(
        "q", QVEC, search_fn=lambda vec, fetch_k: points, top_k=1, fetch_k=5, rerank_fn=rerank_fn
    )
    assert out == []
    assert called is False


def test_empty_search_result_returns_empty():
    out = rag_retrieve_rerank.retrieve_then_rerank(
        "q", QVEC, search_fn=lambda vec, fetch_k: [], top_k=3, fetch_k=10, rerank_fn=_fake_by_length
    )
    assert out == []


def test_empty_query_rejected():
    with pytest.raises(ValueError):
        rag_retrieve_rerank.retrieve_then_rerank(
            "  ", QVEC, search_fn=lambda vec, fetch_k: [], top_k=1, rerank_fn=_fake_by_length
        )


@pytest.mark.parametrize(
    "top_k,fetch_k",
    [(0, 10), (3, 0), (3, rag_retrieve_rerank.MAX_FETCH_K + 1), (10, 5)],
)
def test_bounds_rejected(top_k, fetch_k):
    with pytest.raises(ValueError):
        rag_retrieve_rerank.retrieve_then_rerank(
            "q", QVEC, search_fn=lambda vec, fk: [], top_k=top_k, fetch_k=fetch_k, rerank_fn=_fake_by_length
        )


def test_invalid_query_vector_rejected():
    with pytest.raises(ValueError):
        rag_retrieve_rerank.retrieve_then_rerank(
            "q", [0.1] * 10, search_fn=lambda vec, fk: [], top_k=1, fetch_k=5, rerank_fn=_fake_by_length
        )


def test_candidate_from_point_maps_payload():
    point = _point(0.55, "full chunk body text", article_id=7, title="T", url="u")
    candidate = rag_retrieve_rerank._candidate_from_point(point)

    assert candidate["text"] == "full chunk body text"
    assert candidate["dense_score"] == 0.55
    assert candidate["article_id"] == 7
    assert candidate["title"] == "T"
    assert candidate["snippet"] == "full chunk body text"


def test_make_qdrant_search_fn_over_fetches_without_cap():
    captured = {}

    class FakeClient:
        def collection_exists(self, collection_name):
            return True

        def search(self, *, collection_name, query_vector, limit, with_payload, with_vectors):
            captured.update(collection=collection_name, limit=limit)
            return [_point(0.9, "x")]

    search_fn = rag_retrieve_rerank.make_qdrant_search_fn(FakeClient(), "goodmorning_chunks")
    points = search_fn(QVEC, 100)  # 100 >> rag_retrieval MAX_TOP_K (20)

    assert captured == {"collection": "goodmorning_chunks", "limit": 100}
    assert len(points) == 1
