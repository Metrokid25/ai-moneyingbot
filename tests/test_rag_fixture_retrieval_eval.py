import importlib.util
import re
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


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9]+", text)}


def in_memory_retrieve(query: str, chunks: list[dict], top_k: int = 2) -> list[dict]:
    query_tokens = tokenize(query)
    scored = []
    for chunk in chunks:
        chunk_tokens = tokenize(chunk["embedding_text"])
        score = len(query_tokens & chunk_tokens)
        scored.append(
            {
                "score": score,
                "chunk_id": chunk["chunk_id"],
                "article_id": chunk["article_id"],
                "text": chunk["embedding_text"],
                "source_id": str(chunk["article_id"]),
                "source_path": chunk["metadata"]["source_url"],
                "metadata": chunk["metadata"],
            }
        )
    return sorted(scored, key=lambda item: (-item["score"], item["chunk_id"]))[:top_k]


def test_fixture_retrieval_eval_preserves_expected_sources(tmp_path):
    raw_records = ingest_archive_export.read_jsonl(FIXTURE_PATH)
    normalized, stats = ingest_archive_export.normalize_articles(raw_records)
    normalized_path = tmp_path / "normalized_articles.jsonl"
    ingest_archive_export.write_jsonl(normalized_path, normalized, overwrite=True)

    articles = build_chunks_phase2.read_jsonl_articles(normalized_path)
    chunks = build_chunks_phase2.build_chunks(
        articles,
        threshold=1500,
        chunk_size=1100,
        overlap=180,
    )

    assert stats["normalized_records"] == 2
    assert len(articles) == 2
    assert len(chunks) == 2

    cases = [
        {
            "query": "discount rates equity valuations",
            "expected_article_id": 1001,
            "expected_title": "Rates and stocks",
            "expected_url": "https://example.test/articles/1001",
            "expected_created_at": "2026.05.20.",
        },
        {
            "query": "dollar foreign flows Korean equities",
            "expected_article_id": 1002,
            "expected_title": "FX watch",
            "expected_url": "https://example.test/articles/1002",
            "expected_created_at": "2026.05.21.",
        },
    ]

    for case in cases:
        results = in_memory_retrieve(case["query"], chunks, top_k=2)
        top = results[0]
        metadata = top["metadata"]

        assert top["score"] > 0
        assert top["article_id"] == case["expected_article_id"]
        assert top["source_id"] == str(case["expected_article_id"])
        assert top["source_path"] == case["expected_url"]
        assert metadata["title"] == case["expected_title"]
        assert metadata["url"] == case["expected_url"]
        assert metadata["source_url"] == case["expected_url"]
        assert metadata["created_at"] == case["expected_created_at"]
        assert metadata["collected_at"].startswith("2026-05-")
        assert metadata["source"] == "sample_archive_export"
        assert metadata["content_hash"].startswith("hash-")
