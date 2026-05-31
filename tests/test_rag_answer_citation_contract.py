import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_answering import build_answer_record, build_sources, format_answer_json, format_answer_markdown


SOURCE_FIELD_ORDER = [
    "chunk_id",
    "source_id",
    "source_path",
    "article_id",
    "content_hash",
    "url",
    "source_url",
    "created_at",
    "collected_at",
    "posted_at",
    "source",
    "title",
    "score",
]


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


def test_answer_markdown_citation_labels_order_and_missing_metadata_fallback():
    context_items = [
        {
            "rank": 1,
            "score": 0.91,
            "source_id": "article-2001",
            "source_path": "tests/fixtures/sample_articles.jsonl",
            "chunk_id": "2001:0",
            "article_id": 2001,
            "content_hash": "hash-2001",
            "url": "https://example.test/articles/2001",
            "source_url": "https://example.test/articles/2001",
            "created_at": "2026.05.21.",
            "collected_at": "2026-05-21T08:00:00+09:00",
            "posted_at": "2026.05.21.",
            "source": "sample_archive_export",
            "title": "First source",
            "text": "First source evidence.",
        },
        {
            "rank": 2,
            "score": 0.82,
            "source_id": "",
            "source_path": None,
            "chunk_id": "2002:0",
            "article_id": 2002,
            "content_hash": "hash-2002",
            "url": "",
            "source_url": None,
            "created_at": "",
            "collected_at": None,
            "posted_at": "",
            "source": None,
            "title": "",
            "text": "Second source evidence.",
        },
    ]
    record = build_answer_record(
        query="Which sources are cited?",
        answer="The answer cites both fixture sources.",
        sources=build_sources(context_items),
        model="fake-model",
        top_k=2,
    )

    markdown = format_answer_markdown(record)
    source_lines = [
        line.strip()
        for line in markdown.splitlines()
        if line.lstrip().startswith(("- chunk_id:", "source_id:", "source_path:", "article_id:", "content_hash:", "url:", "source_url:", "created_at:", "collected_at:", "posted_at:", "source:", "title:", "score:"))
    ]

    assert [line.split(":", 1)[0].lstrip("- ") for line in source_lines[:13]] == SOURCE_FIELD_ORDER
    assert [line.split(":", 1)[0].lstrip("- ") for line in source_lines[13:26]] == SOURCE_FIELD_ORDER
    assert source_lines[0] == "- chunk_id: 2001:0"
    assert source_lines[13] == "- chunk_id: 2002:0"
    assert source_lines.index("- chunk_id: 2001:0") < source_lines.index("- chunk_id: 2002:0")

    assert "source_id: unknown" in markdown
    assert "source_path: unknown" in markdown
    assert "url: unknown" in markdown
    assert "source_url: unknown" in markdown
    assert "created_at: unknown" in markdown
    assert "collected_at: unknown" in markdown
    assert "posted_at: unknown" in markdown
    assert "source: unknown" in markdown
    assert "title: unknown" in markdown
