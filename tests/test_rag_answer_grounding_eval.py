import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_answering import assert_answer_grounded, build_answer_record, build_sources, evaluate_answer_grounding


def fixture_context_items():
    return [
        {
            "rank": 1,
            "score": 0.97,
            "source_id": "article-1001",
            "source_path": "tests/fixtures/sample_articles.jsonl",
            "chunk_id": "1001:0",
            "article_id": 1001,
            "content_hash": "hash-rates-001",
            "url": "https://example.test/articles/1001",
            "source_url": "https://example.test/articles/1001",
            "created_at": "2026.05.20.",
            "collected_at": "2026-05-20T08:00:00+09:00",
            "posted_at": "2026.05.20.",
            "source": "sample_archive_export",
            "title": "Rates and stocks",
            "text": "Higher discount rates can pressure equity valuations and liquidity.",
        }
    ]


def test_grounding_eval_accepts_answer_tied_to_fixture_context_and_citations():
    context_items = fixture_context_items()
    record = build_answer_record(
        query="How do rates affect equity valuations?",
        answer="The fixture evidence says higher discount rates can pressure equity valuations.",
        sources=build_sources(context_items),
        model="fake-model",
        top_k=1,
    )

    assert evaluate_answer_grounding(
        record,
        context_items,
        claim_terms=["higher discount rates", "pressure equity valuations"],
    ) == []
    assert_answer_grounded(
        record,
        context_items,
        claim_terms=["higher discount rates", "pressure equity valuations"],
    )


def test_grounding_eval_rejects_unsupported_answer_claims_clearly():
    context_items = fixture_context_items()
    record = build_answer_record(
        query="How do rates affect equity valuations?",
        answer="The evidence says higher discount rates can pressure equity valuations and guarantees a rally.",
        sources=build_sources(context_items),
        model="fake-model",
        top_k=1,
    )

    errors = evaluate_answer_grounding(record, context_items, claim_terms=["guarantees a rally"])

    assert errors == ["unsupported answer claim term not found in evidence: guarantees a rally"]
    with pytest.raises(AssertionError, match="unsupported answer claim term"):
        assert_answer_grounded(record, context_items, claim_terms=["guarantees a rally"])


def test_grounding_eval_rejects_missing_or_unknown_citations():
    context_items = fixture_context_items()
    record = build_answer_record(
        query="How do rates affect equity valuations?",
        answer="Higher discount rates can pressure equity valuations.",
        sources=build_sources(context_items),
        model="fake-model",
        top_k=1,
    )
    record["citations"] = []

    assert evaluate_answer_grounding(record, context_items) == ["answer has sources but no citations"]

    record["citations"] = [{"chunk_id": "unknown:0", "source_id": "unknown"}]
    errors = evaluate_answer_grounding(record, context_items)

    assert errors == ["citation does not match provided context: chunk_id=unknown:0 source_id=unknown"]
