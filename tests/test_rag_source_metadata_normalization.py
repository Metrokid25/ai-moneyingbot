import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rag_answer_context import build_context_item, format_context_markdown
from rag_answering import build_answer_record, build_source, format_answer_markdown, format_context_for_prompt
from rag_chunking import build_chunk_records
from rag_retrieval import format_search_result


SCRIPT_PATH = ROOT / "scripts" / "ingest_archive_export.py"
spec = importlib.util.spec_from_file_location("ingest_archive_export", SCRIPT_PATH)
ingest_archive_export = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ingest_archive_export)

SOURCE_METADATA_TYPES = {
    "source_id": str,
    "source_path": str,
    "chunk_id": str,
    "article_id": int,
    "title": str,
    "url": str,
    "source_url": str,
    "created_at": str,
    "collected_at": str,
    "posted_at": str,
    "source": str,
    "content_hash": str,
}


def _raw_archive_record(**overrides):
    record = {
        "article_id": 1001,
        "title": "Rates and stocks",
        "body_text": "Higher rates can pressure equity valuations through discount rates.",
        "url": "https://example.test/articles/1001",
        "author": "analyst-a",
        "created_at": "2026.05.20.",
        "collected_at": "2026-05-20T09:00:00+09:00",
        "source": "sample_archive_export",
        "content_hash": "hash-1001",
    }
    record.update(overrides)
    return record


def _assert_source_metadata_shape(stage, metadata):
    missing = [field for field in SOURCE_METADATA_TYPES if field not in metadata]
    assert not missing, f"{stage} missing source metadata fields: {', '.join(missing)}"

    type_mismatches = [
        f"{field} expected {expected_type.__name__}, got {type(metadata[field]).__name__}"
        for field, expected_type in SOURCE_METADATA_TYPES.items()
        if not isinstance(metadata[field], expected_type)
    ]
    assert not type_mismatches, f"{stage} source metadata type mismatches: {', '.join(type_mismatches)}"


def test_fixture_source_metadata_is_normalized_across_rag_boundaries():
    article = ingest_archive_export.normalize_article(_raw_archive_record())
    chunk = build_chunk_records(article)[0]
    chunk_payload = {**chunk["metadata"], "text": chunk["embedding_text"]}
    point = SimpleNamespace(score=0.91, payload=chunk_payload)

    retrieval_row = format_search_result(point, rank=1)
    context_item = build_context_item(point, rank=1)
    answer_source = build_source(context_item)

    for stage, metadata in (
        ("chunk metadata", chunk["metadata"]),
        ("retrieval result", retrieval_row),
        ("answer context", context_item),
        ("answer source", answer_source),
    ):
        _assert_source_metadata_shape(stage, metadata)

    assert chunk["metadata"]["source_id"] == "1001"
    assert chunk["metadata"]["source_path"] == "https://example.test/articles/1001"
    assert retrieval_row["source_id"] == "1001"
    assert context_item["source_path"] == "https://example.test/articles/1001"
    assert answer_source["created_at"] == "2026.05.20."
    assert answer_source["collected_at"] == "2026-05-20T09:00:00+09:00"


def test_source_metadata_names_are_visible_in_context_and_answer_outputs():
    article = ingest_archive_export.normalize_article(_raw_archive_record())
    chunk = build_chunk_records(article)[0]
    point = SimpleNamespace(score=0.91, payload={**chunk["metadata"], "text": chunk["embedding_text"]})
    context_item = build_context_item(point, rank=1)

    context_markdown = format_context_markdown("rate question", [context_item], top_k=1)
    prompt_context = format_context_for_prompt([context_item])
    answer_record = build_answer_record(
        query="rate question",
        answer="answer",
        sources=[build_source(context_item)],
        model="gpt-4o-mini",
        top_k=1,
    )
    answer_markdown = format_answer_markdown(answer_record)

    for rendered in (context_markdown, prompt_context, answer_markdown):
        assert "source_id: 1001" in rendered
        assert "source_path: https://example.test/articles/1001" in rendered
        assert "chunk_id: 1001:0" in rendered
        assert "created_at: 2026.05.20." in rendered


def test_source_metadata_shape_failure_names_missing_and_type_mismatch():
    with pytest.raises(AssertionError, match="chunk metadata missing source metadata fields: source_path"):
        _assert_source_metadata_shape("chunk metadata", {"source_id": "1001"})

    metadata = {field: "value" for field in SOURCE_METADATA_TYPES}
    metadata["article_id"] = "1001"
    with pytest.raises(
        AssertionError,
        match="chunk metadata source metadata type mismatches: article_id expected int, got str",
    ):
        _assert_source_metadata_shape("chunk metadata", metadata)
