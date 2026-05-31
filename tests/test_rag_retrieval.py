import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_retrieval import (
    VECTOR_SIZE,
    extract_source_metadata,
    format_search_result,
    format_search_results,
    make_snippet,
    validate_query_vector,
    validate_run_mode,
    validate_top_k,
)


def test_make_snippet_limits_to_250_chars_and_normalizes_whitespace():
    text = "hello\n\n" + ("a" * 300)

    snippet = make_snippet(text)

    assert snippet.startswith("hello ")
    assert len(snippet) == 250
    assert "\n" not in snippet


def test_format_search_result_handles_payload_fields():
    point = SimpleNamespace(
        score=0.87,
        payload={
            "chunk_id": "1:0",
            "article_id": 1,
            "content_hash": "hash-1",
            "url": "https://example.test/articles/1",
            "source_url": "https://example.test/articles/1",
            "created_at": "2026.05.18.",
            "collected_at": "2026-05-18T09:00:00+09:00",
            "posted_at": "2026.05.18.",
            "title": "title",
            "text": "body text",
            "source": "source",
        },
    )

    row = format_search_result(point, rank=1)

    assert row == {
        "rank": 1,
        "score": 0.87,
        "chunk_id": "1:0",
        "article_id": 1,
        "source_id": None,
        "source_path": None,
        "content_hash": "hash-1",
        "url": "https://example.test/articles/1",
        "source_url": "https://example.test/articles/1",
        "created_at": "2026.05.18.",
        "collected_at": "2026-05-18T09:00:00+09:00",
        "posted_at": "2026.05.18.",
        "title": "title",
        "snippet": "body text",
        "source": "source",
    }


def test_format_search_result_handles_missing_payload_fields():
    row = format_search_result(SimpleNamespace(score=0.1, payload={}), rank=3)

    assert row["rank"] == 3
    assert row["chunk_id"] is None
    assert row["article_id"] is None
    assert row["content_hash"] is None
    assert row["url"] is None
    assert row["source_url"] is None
    assert row["created_at"] is None
    assert row["collected_at"] is None
    assert row["title"] is None
    assert row["snippet"] == ""
    assert row["source"] is None


def test_format_search_results_preserves_backend_source_order_and_ranks():
    points = [
        SimpleNamespace(
            score=0.91,
            payload={
                "chunk_id": "300:0",
                "article_id": 300,
                "source_id": "300",
                "source_path": "https://example.test/articles/300",
                "url": "https://example.test/articles/300",
                "source_url": "https://example.test/articles/300",
                "title": "third article",
                "text": "highest ranked retrieval evidence",
                "source": "fixture",
            },
        ),
        SimpleNamespace(
            score=0.91,
            payload={
                "chunk_id": "100:0",
                "article_id": 100,
                "source_id": "100",
                "source_path": "https://example.test/articles/100",
                "url": "https://example.test/articles/100",
                "source_url": "https://example.test/articles/100",
                "title": "first article",
                "text": "same score but backend ranked second",
                "source": "fixture",
            },
        ),
        SimpleNamespace(
            score=0.72,
            payload={
                "chunk_id": "200:0",
                "article_id": 200,
                "source_id": "200",
                "source_path": "https://example.test/articles/200",
                "url": "https://example.test/articles/200",
                "source_url": "https://example.test/articles/200",
                "title": "second article",
                "text": "lower ranked retrieval evidence",
                "source": "fixture",
            },
        ),
    ]

    rows = format_search_results(points)

    assert [row["rank"] for row in rows] == [1, 2, 3]
    assert [row["chunk_id"] for row in rows] == ["300:0", "100:0", "200:0"]
    assert [row["source_id"] for row in rows] == ["300", "100", "200"]
    assert [row["source_url"] for row in rows] == [
        "https://example.test/articles/300",
        "https://example.test/articles/100",
        "https://example.test/articles/200",
    ]


def test_format_search_results_ranks_multiple_candidate_chunks_by_backend_score_order():
    points = [
        SimpleNamespace(
            score=0.97,
            payload={
                "chunk_id": "rate-policy:0",
                "article_id": 10,
                "title": "Interest rate policy and liquidity",
                "text": "Interest rate policy and liquidity signals for equities",
            },
        ),
        SimpleNamespace(
            score=0.64,
            payload={
                "chunk_id": "chip-cycle:0",
                "article_id": 20,
                "title": "Semiconductor cycle update",
                "text": "Chip demand and earnings guidance",
            },
        ),
        SimpleNamespace(
            score=0.22,
            payload={
                "chunk_id": "housing-credit:0",
                "article_id": 30,
                "title": "Housing credit conditions",
                "text": "Mortgage credit and property transaction trends",
            },
        ),
    ]

    rows = format_search_results(points)

    assert [row["rank"] for row in rows] == [1, 2, 3]
    assert [row["chunk_id"] for row in rows] == [
        "rate-policy:0",
        "chip-cycle:0",
        "housing-credit:0",
    ]
    assert [row["score"] for row in rows] == [0.97, 0.64, 0.22]
    assert rows[0]["score"] > rows[1]["score"] > rows[2]["score"]


def test_extract_source_metadata_accepts_nested_metadata_fallback():
    payload = {
        "metadata": {
            "chunk_id": "1:0",
            "article_id": 1,
            "content_hash": "hash-1",
            "url": "https://example.test/articles/1",
            "source_url": "https://example.test/articles/1",
            "created_at": "2026.05.18.",
            "collected_at": "2026-05-18T09:00:00+09:00",
            "posted_at": "2026.05.18.",
            "source": "source",
            "title": "title",
        }
    }

    metadata = extract_source_metadata(payload)

    assert metadata["chunk_id"] == "1:0"
    assert metadata["content_hash"] == "hash-1"
    assert metadata["url"] == "https://example.test/articles/1"
    assert metadata["created_at"] == "2026.05.18."


@pytest.mark.parametrize("top_k", [1, 5, 20])
def test_validate_top_k_accepts_range(top_k):
    validate_top_k(top_k)


@pytest.mark.parametrize("top_k", [0, 21])
def test_validate_top_k_rejects_out_of_range(top_k):
    with pytest.raises(ValueError, match="--top-k"):
        validate_top_k(top_k)


def test_validate_run_mode_rejects_dry_run_and_execute():
    with pytest.raises(ValueError, match="mutually exclusive"):
        validate_run_mode(dry_run=True, execute=True)


def test_validate_run_mode_rejects_no_execute_without_dry_run():
    with pytest.raises(ValueError, match="without --execute"):
        validate_run_mode(dry_run=False, execute=False)


def test_validate_run_mode_accepts_dry_run():
    validate_run_mode(dry_run=True, execute=False)


def test_validate_run_mode_accepts_execute():
    validate_run_mode(dry_run=False, execute=True)


def test_validate_query_vector_accepts_1024_vector():
    vector = validate_query_vector(np.ones(VECTOR_SIZE, dtype=np.float32))

    assert vector.shape == (VECTOR_SIZE,)
    assert vector.dtype == np.float32


def test_validate_query_vector_rejects_wrong_dimension():
    with pytest.raises(ValueError, match="dimension mismatch"):
        validate_query_vector(np.ones(3, dtype=np.float32))


def test_validate_query_vector_rejects_nan():
    vector = np.ones(VECTOR_SIZE, dtype=np.float32)
    vector[0] = np.nan

    with pytest.raises(ValueError, match="NaN or inf"):
        validate_query_vector(vector)
