import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_chunking import (
    REQUIRED_METADATA_FIELDS,
    build_chunk_records,
    build_embedding_text,
    parse_year_month,
    split_text_into_chunks,
    validate_chunk_metadata,
)


def _article(**overrides):
    data = {
        "article_id": 169913,
        "title": "하방경직성",
        "posted_at": "11:47",
        "created_at": "2026.05.20.",
        "collected_at": "2026-05-20T09:00:00+09:00",
        "author": "굿모닝",
        "clean_text": "하방경직성\n\n-엘앤에프",
        "status": "BODY_COLLECTED",
        "url": "https://example.test/articles/169913",
        "source_url": "https://example.test/articles/169913",
        "content_hash": "hash-169913",
    }
    data.update(overrides)
    return data


def test_short_text_is_one_chunk():
    chunks = split_text_into_chunks("short memo")
    assert chunks == ["short memo"]


def test_under_threshold_is_one_chunk():
    text = "a" * 1499
    chunks = split_text_into_chunks(text, threshold=1500)
    assert chunks == [text]


def test_over_threshold_is_multiple_chunks():
    text = "a" * 2500
    chunks = split_text_into_chunks(text, threshold=1500, chunk_size=1100, overlap=180)
    assert len(chunks) > 1
    assert all(chunks)


def test_fallback_split_applies_overlap():
    text = "".join(str(i % 10) for i in range(2500))
    chunks = split_text_into_chunks(text, threshold=100, chunk_size=1000, overlap=200)
    assert chunks[0][-200:] == chunks[1][:200]


def test_paragraph_split_prefers_paragraph_boundaries():
    p1 = "a" * 600
    p2 = "b" * 600
    p3 = "c" * 600
    text = f"{p1}\n\n{p2}\n\n{p3}"
    chunks = split_text_into_chunks(text, threshold=100, chunk_size=1300, overlap=180)
    assert chunks == [f"{p1}\n\n{p2}", p3]


def test_parse_year_month_date_format():
    assert parse_year_month("2026.05.15.") == (2026, 5)


def test_parse_year_month_time_format_is_null():
    assert parse_year_month("11:47") == (None, None)


def test_parse_year_month_iso_format():
    # 2026-07-02: member_api 경로가 posted_at을 ISO 형식으로 저장 → 파싱 지원
    assert parse_year_month("2026-05-15") == (2026, 5)
    assert parse_year_month("2026-07-02 11:49:39") == (2026, 7)


def test_parse_year_month_unknown_format_is_null():
    assert parse_year_month("어제") == (None, None)
    assert parse_year_month("2026/05/15") == (None, None)


def test_chunk_id_rule():
    records = build_chunk_records(_article(article_id=42, clean_text="hello"))
    assert records[0]["chunk_id"] == "42:0"
    assert records[0]["metadata"]["chunk_id"] == "42:0"


def test_metadata_required_fields_included():
    record = build_chunk_records(_article())[0]
    assert REQUIRED_METADATA_FIELDS <= set(record["metadata"])
    validate_chunk_metadata(record["metadata"], chunk_id=record["chunk_id"])


def test_chunk_metadata_validation_rejects_missing_field():
    record = build_chunk_records(_article())[0]
    del record["metadata"]["source_url"]

    with pytest.raises(ValueError, match="metadata missing required fields: source_url"):
        validate_chunk_metadata(record["metadata"], chunk_id=record["chunk_id"])


def test_chunk_metadata_validation_rejects_empty_required_field():
    record = build_chunk_records(_article())[0]
    record["metadata"]["content_hash"] = " "

    with pytest.raises(ValueError, match="metadata empty required fields: content_hash"):
        validate_chunk_metadata(record["metadata"], chunk_id=record["chunk_id"])


def test_chunk_metadata_validation_rejects_type_mismatch():
    record = build_chunk_records(_article())[0]
    record["metadata"]["article_id"] = "169913"

    with pytest.raises(ValueError, match="article_id expected int, got str"):
        validate_chunk_metadata(record["metadata"], chunk_id=record["chunk_id"])


def test_chunk_metadata_validation_rejects_chunk_id_mismatch():
    record = build_chunk_records(_article())[0]
    record["metadata"]["chunk_id"] = "169913:99"

    with pytest.raises(ValueError, match="metadata chunk_id mismatch"):
        validate_chunk_metadata(record["metadata"], chunk_id=record["chunk_id"])


def test_ingest_metadata_fields_are_preserved():
    record = build_chunk_records(
        _article(
            article_id=1001,
            source="sample_archive_export",
            url="https://example.test/articles/1001",
            source_url="https://example.test/articles/1001",
            created_at="2026.05.20.",
            collected_at="2026-05-20T09:00:00+09:00",
            content_hash="hash-1001",
        )
    )[0]

    assert record["metadata"]["article_id"] == 1001
    assert record["metadata"]["source"] == "sample_archive_export"
    assert record["metadata"]["url"] == "https://example.test/articles/1001"
    assert record["metadata"]["source_url"] == "https://example.test/articles/1001"
    assert record["metadata"]["created_at"] == "2026.05.20."
    assert record["metadata"]["collected_at"] == "2026-05-20T09:00:00+09:00"
    assert record["metadata"]["content_hash"] == "hash-1001"


def test_body_len_zero_is_preserved_with_title():
    records = build_chunk_records(_article(title="제목만 있음", clean_text=""))
    assert len(records) == 1
    assert records[0]["embedding_text"] == "제목만 있음"
    assert records[0]["metadata"]["body_len"] == 0


def test_build_embedding_text_handles_none():
    assert build_embedding_text(None, "body") == "body"
    assert build_embedding_text("title", None) == "title"
