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


def test_golden_question_fixture_is_valid_jsonl():
    rows = load_jsonl(GOLDEN_FIXTURE_PATH)
    ids = [row["id"] for row in rows]

    assert len(rows) >= 2
    assert len(ids) == len(set(ids))
    for row in rows:
        assert row["id"].startswith("golden-")
        assert row["question"].strip()
        assert isinstance(row["expected_keywords"], list)
        assert row["expected_keywords"]
        assert isinstance(row["expected_sources"], list)
        assert row["expected_sources"]


def test_golden_question_expected_sources_have_required_metadata():
    required_source_fields = {"source_id", "article_id", "title", "url", "chunk_id"}

    for row in load_jsonl(GOLDEN_FIXTURE_PATH):
        for source in row["expected_sources"]:
            assert required_source_fields <= set(source)
            assert source["source_id"] == str(source["article_id"])
            assert source["chunk_id"].startswith(f"{source['article_id']}:")
            assert source["title"].strip()
            assert source["url"].startswith("https://example.test/articles/")


def test_golden_questions_match_sample_chunk_sources(tmp_path):
    rows = load_jsonl(GOLDEN_FIXTURE_PATH)
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in build_sample_chunks(tmp_path)}

    for row in rows:
        question_tokens = tokenize(row["question"])
        expected_keyword_tokens = set()
        for keyword in row["expected_keywords"]:
            expected_keyword_tokens.update(tokenize(keyword))

        for expected_source in row["expected_sources"]:
            chunk = chunks_by_id[expected_source["chunk_id"]]
            metadata = chunk["metadata"]
            searchable_text = f"{chunk['embedding_text']} {metadata['title']}"
            searchable_tokens = tokenize(searchable_text)

            assert chunk["article_id"] == expected_source["article_id"]
            assert metadata["article_id"] == expected_source["article_id"]
            assert metadata["chunk_id"] == expected_source["chunk_id"]
            assert metadata["title"] == expected_source["title"]
            assert metadata["url"] == expected_source["url"]
            assert metadata["source_url"] == expected_source["url"]
            assert question_tokens & searchable_tokens
            assert expected_keyword_tokens <= searchable_tokens
