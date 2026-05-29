import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_answering import build_answer_record, build_sources, format_answer_json, format_answer_markdown


def test_answer_output_preserves_source_citation_metadata():
    context_items = [
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
            "text": "Higher discount rates can pressure equity valuations.",
        }
    ]

    sources = build_sources(context_items)
    record = build_answer_record(
        query="How do rates affect equity valuations?",
        answer="Rates are cited from the fixture evidence.",
        sources=sources,
        model="fake-model",
        top_k=1,
    )

    markdown = format_answer_markdown(record)
    payload = json.loads(format_answer_json(record))

    source = payload["sources"][0]
    assert source["source_id"] == "article-1001"
    assert source["source_path"] == "tests/fixtures/sample_articles.jsonl"
    assert source["chunk_id"] == "1001:0"
    assert source["title"] == "Rates and stocks"
    assert source["url"] == "https://example.test/articles/1001"

    assert "## " in markdown
    assert "chunk_id: 1001:0" in markdown
    assert "source_id: article-1001" in markdown
    assert "source_path: tests/fixtures/sample_articles.jsonl" in markdown
    assert "title: Rates and stocks" in markdown
    assert "url: https://example.test/articles/1001" in markdown
