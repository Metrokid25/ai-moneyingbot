import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "sample_articles.jsonl"


def load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ingest_archive_export = load_script_module(
    "ingest_archive_export", ROOT / "scripts" / "ingest_archive_export.py"
)
build_chunks_phase2 = load_script_module(
    "build_chunks_phase2", ROOT / "scripts" / "build_chunks_phase2.py"
)


def test_fixture_jsonl_ingest_to_chunking_retrieval_ready_smoke(tmp_path):
    raw_records = ingest_archive_export.read_jsonl(FIXTURE_PATH)
    normalized, ingest_stats = ingest_archive_export.normalize_articles(raw_records)
    normalized_path = tmp_path / "normalized_articles.jsonl"

    ingest_archive_export.write_jsonl(normalized_path, normalized, overwrite=True)

    assert ingest_stats["input_records"] == 4
    assert ingest_stats["normalized_records"] == 2
    assert ingest_stats["duplicate_article_id_skipped"] == 1
    assert ingest_stats["duplicate_content_hash_skipped"] == 1
    assert normalized_path.exists()

    articles = build_chunks_phase2.read_jsonl_articles(normalized_path)
    chunks = build_chunks_phase2.build_chunks(
        articles,
        threshold=1500,
        chunk_size=1100,
        overlap=180,
    )
    chunks_path = tmp_path / "chunks.jsonl"
    build_chunks_phase2.write_jsonl(chunks_path, chunks, overwrite=True)
    chunk_rows = [
        json.loads(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(articles) == 2
    assert len(chunk_rows) == 2
    assert build_chunks_phase2.summarize(articles, chunks)["chunks_missing_required_metadata"] == 0

    first_chunk = chunk_rows[0]
    metadata = first_chunk["metadata"]
    assert first_chunk["chunk_id"] == "1001:0"
    assert first_chunk["article_id"] == 1001
    assert first_chunk["embedding_text"].strip()
    assert metadata["article_id"] == 1001
    assert metadata["title"] == "Rates and stocks"
    assert metadata["url"] == "https://example.test/articles/1001"
    assert metadata["source_url"] == "https://example.test/articles/1001"
    assert metadata["source"] == "sample_archive_export"
    assert metadata["created_at"] == "2026.05.20."
    assert metadata["collected_at"] == "2026-05-20T09:00:00+09:00"
    assert metadata["content_hash"] == "hash-1001"

    retrieval_ready = [
        {
            "chunk_id": chunk["chunk_id"],
            "article_id": chunk["article_id"],
            "text": chunk["embedding_text"],
            "payload": chunk["metadata"],
        }
        for chunk in chunk_rows
    ]
    assert retrieval_ready[0]["payload"]["source_url"] == "https://example.test/articles/1001"
    assert retrieval_ready[0]["payload"]["content_hash"] == "hash-1001"
