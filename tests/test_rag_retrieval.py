from types import SimpleNamespace

import numpy as np
import pytest

from rag_retrieval import (
    VECTOR_SIZE,
    format_search_result,
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
    assert row["title"] is None
    assert row["snippet"] == ""
    assert row["source"] is None


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
