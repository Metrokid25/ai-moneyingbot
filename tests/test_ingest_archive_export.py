import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "ingest_archive_export.py"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "sample_articles.jsonl"

sys.path.insert(0, str(ROOT / "src"))
from rag_chunking import REQUIRED_METADATA_FIELDS, validate_chunk_metadata

spec = importlib.util.spec_from_file_location("ingest_archive_export", SCRIPT_PATH)
ingest_archive_export = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ingest_archive_export)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )


def _record(**overrides):
    record = {
        "article_id": 42,
        "title": "Market memo",
        "body_text": "Body text for retrieval.",
        "url": "https://example.test/articles/42",
        "author": "writer",
        "created_at": "2026.05.20.",
        "collected_at": "2026-05-20T09:00:00+09:00",
        "source": "sample_archive_export",
        "content_hash": "hash-42",
    }
    record.update(overrides)
    return record


def test_read_jsonl_requires_all_fields(tmp_path):
    path = tmp_path / "missing.jsonl"
    record = _record()
    del record["content_hash"]
    _write_jsonl(path, [record])

    with pytest.raises(ValueError, match="line 1: missing required fields: content_hash"):
        ingest_archive_export.read_jsonl(path)


def test_duplicate_article_id_and_content_hash_are_skipped():
    records = [
        _record(article_id=1, content_hash="hash-1"),
        _record(article_id=1, content_hash="hash-duplicate-id"),
        _record(article_id=2, content_hash="hash-1"),
        _record(article_id=3, content_hash="hash-3"),
    ]

    normalized, stats = ingest_archive_export.normalize_articles(records)

    assert [record["article_id"] for record in normalized] == [1, 3]
    assert stats["duplicate_article_id_skipped"] == 1
    assert stats["duplicate_content_hash_skipped"] == 1


def test_normalized_record_preserves_url_dates_source_and_hash():
    normalized, _stats = ingest_archive_export.normalize_articles([_record()])
    article = normalized[0]

    assert article["clean_text"] == "Body text for retrieval."
    assert article["posted_at"] == "2026.05.20."
    assert article["created_at"] == "2026.05.20."
    assert article["collected_at"] == "2026-05-20T09:00:00+09:00"
    assert article["url"] == "https://example.test/articles/42"
    assert article["source_url"] == "https://example.test/articles/42"
    assert article["source"] == "sample_archive_export"
    assert article["content_hash"] == "hash-42"
    assert article["status"] == "BODY_COLLECTED"


def test_dry_run_cli_summarizes_fixture_without_writing(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input",
            str(FIXTURE_PATH),
            "--dry-run",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "input_records: 4" in result.stdout
    assert "normalized_records: 2" in result.stdout
    assert "duplicate_article_id_skipped: 1" in result.stdout
    assert "duplicate_content_hash_skipped: 1" in result.stdout


def test_write_cli_outputs_normalized_jsonl(tmp_path):
    output = tmp_path / "normalized.jsonl"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input",
            str(FIXTURE_PATH),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["article_id"] == 1001
    assert rows[0]["url"] == "https://example.test/articles/1001"


def test_normalized_output_can_feed_chunk_builder(tmp_path):
    normalized = tmp_path / "normalized.jsonl"
    chunks_path = tmp_path / "chunks.jsonl"

    ingest_result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input",
            str(FIXTURE_PATH),
            "--output",
            str(normalized),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert ingest_result.returncode == 0

    chunk_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_chunks_phase2.py"),
            "--input-jsonl",
            str(normalized),
            "--out-path",
            str(chunks_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert chunk_result.returncode == 0
    chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines()]
    assert len(chunks) == 2
    assert chunks[0]["article_id"] == 1001
    assert chunks[0]["metadata"]["content_hash"] == "hash-1001"
    assert chunks[0]["metadata"]["url"] == "https://example.test/articles/1001"
    assert chunks[0]["metadata"]["created_at"] == "2026.05.20."
    assert chunks[0]["metadata"]["collected_at"] == "2026-05-20T09:00:00+09:00"
    assert chunks[0]["metadata"]["source"] == "sample_archive_export"

    for chunk in chunks:
        assert REQUIRED_METADATA_FIELDS <= set(chunk["metadata"])
        validate_chunk_metadata(chunk["metadata"], chunk_id=chunk["chunk_id"])
