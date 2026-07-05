import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GOLDEN_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "rag_golden_questions.jsonl"
SAMPLE_ARTICLES_PATH = ROOT / "tests" / "fixtures" / "sample_articles.jsonl"


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


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9]+", text)}


def build_sample_chunks(tmp_path: Path) -> list[dict]:
    raw_records = ingest_archive_export.read_jsonl(SAMPLE_ARTICLES_PATH)
    normalized, stats = ingest_archive_export.normalize_articles(raw_records)
    normalized_path = tmp_path / "normalized_articles.jsonl"
    ingest_archive_export.write_jsonl(normalized_path, normalized, overwrite=True)

    assert stats["normalized_records"] == 2
    articles = build_chunks_phase2.read_jsonl_articles(normalized_path)
    return build_chunks_phase2.build_chunks(
        articles,
        threshold=1500,
        chunk_size=1100,
        overlap=180,
    )


def retrieval_ready_payload(chunk: dict) -> dict:
    metadata = chunk["metadata"]
    return {
        "chunk_id": chunk["chunk_id"],
        "article_id": chunk["article_id"],
        "source_id": str(chunk["article_id"]),
        "source_path": metadata["source_url"],
        "title": metadata["title"],
        "url": metadata["url"],
        "source_url": metadata["source_url"],
        "created_at": metadata["created_at"],
        "collected_at": metadata["collected_at"],
        "source": metadata["source"],
        "content_hash": metadata["content_hash"],
        "text": chunk["embedding_text"],
        "metadata": metadata,
    }


def in_memory_retrieve(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    query_tokens = tokenize(query)
    scored = []

    for chunk in chunks:
        payload = retrieval_ready_payload(chunk)
        searchable_text = f"{payload['title']} {payload['text']}"
        chunk_tokens = tokenize(searchable_text)
        matched_tokens = query_tokens & chunk_tokens
        scored.append(
            {
                "score": len(matched_tokens),
                "matched_tokens": sorted(matched_tokens),
                **payload,
            }
        )

    return sorted(scored, key=lambda item: (-item["score"], item["chunk_id"]))[:top_k]


def test_golden_questions_retrieve_expected_sources_in_top_k(tmp_path):
    chunks = build_sample_chunks(tmp_path)
    cases = load_jsonl(GOLDEN_FIXTURE_PATH)

    assert len(chunks) == 2
    assert cases

    for case in cases:
        results = in_memory_retrieve(case["question"], chunks, top_k=2)

        assert any(result["score"] > 0 for result in results)
        for expected_source in case["expected_sources"]:
            matched = [
                result
                for result in results
                if result["chunk_id"] == expected_source["chunk_id"]
            ]

            assert matched, f"{case['id']} did not retrieve {expected_source['chunk_id']}"
            result = matched[0]
            assert result["score"] > 0
            assert result["source_id"] == expected_source["source_id"]
            assert result["article_id"] == expected_source["article_id"]
            assert result["title"] == expected_source["title"]
            assert result["url"] == expected_source["url"]
            assert result["source_url"] == expected_source["url"]
            assert result["source_path"] == expected_source["url"]
            assert result["metadata"]["chunk_id"] == expected_source["chunk_id"]
            assert result["metadata"]["article_id"] == expected_source["article_id"]


def test_retrieval_ranks_expected_source_first_for_each_golden_question(tmp_path):
    chunks = build_sample_chunks(tmp_path)

    for case in load_jsonl(GOLDEN_FIXTURE_PATH):
        expected_chunk_ids = {
            source["chunk_id"] for source in case["expected_sources"]
        }
        results = in_memory_retrieve(case["question"], chunks, top_k=1)

        assert results[0]["chunk_id"] in expected_chunk_ids
        assert results[0]["score"] > 0
