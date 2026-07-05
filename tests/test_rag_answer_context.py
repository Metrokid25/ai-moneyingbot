from pathlib import Path
from types import SimpleNamespace

import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_answer_context import (
    build_context_item,
    build_context_items,
    format_context_json,
    format_context_markdown,
    truncate_text,
    truncate_text_tokens,
    validate_context_top_k,
    validate_output_path,
)


def test_truncate_text_limits_and_normalizes_whitespace():
    text = "hello\n\n" + ("a" * 1000)

    snippet = truncate_text(text, max_chars=20)

    assert snippet.startswith("hello ")
    assert len(snippet) == 20
    assert "\n" not in snippet


def test_truncate_text_keeps_short_text():
    assert truncate_text("short text", max_chars=20) == "short text"


def test_truncate_text_tokens_limits_and_normalizes_whitespace():
    text = "alpha\n beta   gamma delta"

    snippet = truncate_text_tokens(text, max_tokens=3)

    assert snippet == "alpha beta gamma"


def test_truncate_text_tokens_rejects_negative_budget():
    with pytest.raises(ValueError, match="max_tokens"):
        truncate_text_tokens("text", max_tokens=-1)


def test_build_context_item_handles_missing_payload_fields():
    item = build_context_item(SimpleNamespace(score=0.1, payload={}), rank=2)

    assert item["rank"] == 2
    assert item["score"] == 0.1
    assert item["chunk_id"] is None
    assert item["article_id"] is None
    assert item["title"] is None
    assert item["posted_at"] is None
    assert item["year"] is None
    assert item["month"] is None
    assert item["source"] is None
    assert item["text"] == ""
    assert item["empty_text"] is True


def test_build_context_item_extracts_payload_fields():
    point = SimpleNamespace(
        score=0.87,
        payload={
            "chunk_id": "1:0",
            "article_id": 1,
            "title": "title",
            "content_hash": "hash-1",
            "url": "https://example.test/articles/1",
            "source_url": "https://example.test/articles/1",
            "created_at": "2026.05.18.",
            "collected_at": "2026-05-18T09:00:00+09:00",
            "posted_at": "2026.05.18.",
            "year": 2026,
            "month": 5,
            "source": "source",
            "text": "body text",
        },
    )

    item = build_context_item(point, rank=1)

    assert item == {
        "rank": 1,
        "score": 0.87,
        "source_id": None,
        "source_path": None,
        "chunk_id": "1:0",
        "article_id": 1,
        "title": "title",
        "content_hash": "hash-1",
        "url": "https://example.test/articles/1",
        "source_url": "https://example.test/articles/1",
        "created_at": "2026.05.18.",
        "collected_at": "2026-05-18T09:00:00+09:00",
        "posted_at": "2026.05.18.",
        "year": 2026,
        "month": 5,
        "source": "source",
        "text": "body text",
        "empty_text": False,
    }


def test_build_context_items_assigns_ranks():
    points = [
        SimpleNamespace(score=0.2, payload={"text": "one"}),
        SimpleNamespace(score=0.1, payload={"text": "two"}),
    ]

    items = build_context_items(points)

    assert [item["rank"] for item in items] == [1, 2]


def test_build_context_items_deduplicates_retrieved_chunks_for_same_source_article():
    points = [
        SimpleNamespace(
            score=0.95,
            payload={
                "chunk_id": "1001:0",
                "article_id": 1001,
                "title": "Rates",
                "url": "https://example.test/articles/1001",
                "text": "first chunk",
            },
        ),
        SimpleNamespace(
            score=0.93,
            payload={
                "chunk_id": "1001:1",
                "article_id": 1001,
                "title": "Rates",
                "url": "https://example.test/articles/1001",
                "text": "duplicate article chunk",
            },
        ),
        SimpleNamespace(
            score=0.91,
            payload={
                "chunk_id": "1002:0",
                "article_id": 1002,
                "title": "FX",
                "url": "https://example.test/articles/1002",
                "text": "second article",
            },
        ),
    ]

    items = build_context_items(points)

    assert [item["chunk_id"] for item in items] == ["1001:0", "1002:0"]
    assert [item["rank"] for item in items] == [1, 2]
    assert "duplicate article chunk" not in [item["text"] for item in items]


def test_build_context_items_applies_compact_text_token_budget_across_candidates():
    points = [
        SimpleNamespace(score=0.9, payload={"chunk_id": "1:0", "text": "alpha beta gamma delta"}),
        SimpleNamespace(score=0.8, payload={"chunk_id": "2:0", "text": "epsilon zeta eta theta"}),
        SimpleNamespace(score=0.7, payload={"chunk_id": "3:0", "text": "iota kappa lambda mu"}),
    ]

    items = build_context_items(points, max_text_tokens=7)

    assert [item["rank"] for item in items] == [1, 2]
    assert [item["chunk_id"] for item in items] == ["1:0", "2:0"]
    assert items[0]["text"] == "alpha beta gamma delta"
    assert items[1]["text"] == "epsilon zeta eta"
    assert sum(len(item["text"].split()) for item in items) == 7


def test_build_context_items_rejects_negative_text_token_budget():
    with pytest.raises(ValueError, match="max_text_tokens"):
        build_context_items([], max_text_tokens=-1)


def test_markdown_context_contains_question_rank_title_chunk_score_and_text():
    result = {
        "rank": 1,
        "score": 0.87,
        "chunk_id": "1:0",
        "article_id": 1,
        "title": "title",
        "content_hash": "hash-1",
        "url": "https://example.test/articles/1",
        "source_url": "https://example.test/articles/1",
        "created_at": "2026.05.18.",
        "collected_at": "2026-05-18T09:00:00+09:00",
        "posted_at": "2026.05.18.",
        "year": 2026,
        "month": 5,
        "source": "source",
        "text": "body text",
        "empty_text": False,
    }

    markdown = format_context_markdown("question", [result], top_k=5)

    assert "Question: question" in markdown
    assert "1. title" in markdown
    assert "chunk_id: 1:0" in markdown
    assert "content_hash: hash-1" in markdown
    assert "url: https://example.test/articles/1" in markdown
    assert "source_url: https://example.test/articles/1" in markdown
    assert "created_at: 2026.05.18." in markdown
    assert "collected_at: 2026-05-18T09:00:00+09:00" in markdown
    assert "score: 0.87" in markdown
    assert "body text" in markdown


def test_json_context_shape():
    result = build_context_item(SimpleNamespace(score=0.5, payload={"chunk_id": "2:0", "text": "text"}), rank=1)

    payload = json.loads(format_context_json("question", [result], top_k=1))

    assert payload["question"] == "question"
    assert payload["top_k"] == 1
    assert payload["results"][0]["rank"] == 1
    assert payload["results"][0]["score"] == 0.5
    assert payload["results"][0]["chunk_id"] == "2:0"
    assert payload["results"][0]["text"] == "text"
    assert payload["results"][0]["empty_text"] is False


def test_build_context_item_accepts_nested_metadata_fallback():
    point = SimpleNamespace(
        score=0.87,
        payload={
            "text": "body text",
            "metadata": {
                "chunk_id": "1:0",
                "article_id": 1,
                "content_hash": "hash-1",
                "url": "https://example.test/articles/1",
                "source_url": "https://example.test/articles/1",
                "created_at": "2026.05.18.",
                "collected_at": "2026-05-18T09:00:00+09:00",
                "posted_at": "2026.05.18.",
                "title": "title",
                "source": "source",
            },
        },
    )

    item = build_context_item(point, rank=1)

    assert item["chunk_id"] == "1:0"
    assert item["content_hash"] == "hash-1"
    assert item["url"] == "https://example.test/articles/1"
    assert item["created_at"] == "2026.05.18."
    assert item["text"] == "body text"


@pytest.mark.parametrize("top_k", [1, 5, 10])
def test_validate_context_top_k_accepts_range(top_k):
    validate_context_top_k(top_k)


@pytest.mark.parametrize("top_k", [0, 11])
def test_validate_context_top_k_rejects_out_of_range(top_k):
    with pytest.raises(ValueError, match="--top-k"):
        validate_context_top_k(top_k)


def test_validate_output_path_rejects_existing_without_overwrite(tmp_path):
    out_path = tmp_path / "context.md"
    out_path.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        validate_output_path(out_path, overwrite=False)
