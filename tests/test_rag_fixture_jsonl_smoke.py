import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "sample_articles.jsonl"
EVAL_QUESTIONS_PATH = ROOT / "tests" / "fixtures" / "rag_eval_questions.jsonl"
GOLDEN_QUESTIONS_PATH = ROOT / "tests" / "fixtures" / "rag_golden_questions.jsonl"


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


def load_jsonl_rows(path: Path) -> list[tuple[int, dict]]:
    rows = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if line.strip():
            value = json.loads(line)
            assert isinstance(value, dict), f"{path}:{line_number} must be a JSON object"
            rows.append((line_number, value))
    assert rows, f"{path} must contain at least one fixture row"
    return rows


def assert_required_fields(path: Path, line_number: int, row: dict, required: set[str]) -> None:
    missing = sorted(required - set(row))
    assert not missing, f"{path}:{line_number} missing required fields: {missing}"


def assert_string_field(
    path: Path,
    line_number: int,
    row: dict,
    field: str,
    *,
    allow_empty: bool = False,
) -> None:
    value = row[field]
    assert isinstance(value, str), f"{path}:{line_number} field {field!r} must be str"
    if not allow_empty:
        assert value.strip(), f"{path}:{line_number} field {field!r} must not be blank"


def assert_string_list(path: Path, line_number: int, row: dict, field: str) -> None:
    value = row[field]
    assert isinstance(value, list), f"{path}:{line_number} field {field!r} must be list"
    assert value, f"{path}:{line_number} field {field!r} must not be empty"
    for index, item in enumerate(value):
        assert isinstance(item, str), (
            f"{path}:{line_number} field {field!r}[{index}] must be str"
        )
        assert item.strip(), f"{path}:{line_number} field {field!r}[{index}] must not be blank"


def test_rag_jsonl_fixture_schemas_are_stable():
    article_required = {
        "article_id",
        "title",
        "body_text",
        "url",
        "author",
        "created_at",
        "collected_at",
        "source",
        "content_hash",
    }
    for line_number, row in load_jsonl_rows(FIXTURE_PATH):
        assert_required_fields(FIXTURE_PATH, line_number, row, article_required)
        assert isinstance(row["article_id"], int), (
            f"{FIXTURE_PATH}:{line_number} field 'article_id' must be int"
        )
        for field in article_required - {"article_id"}:
            assert_string_field(FIXTURE_PATH, line_number, row, field)
        assert row["url"].startswith("https://"), (
            f"{FIXTURE_PATH}:{line_number} field 'url' must be absolute https URL"
        )

    eval_required = {
        "id",
        "question",
        "category",
        "expected_topics",
        "expected_keywords",
        "expected_article_ids",
        "expected_chunk_ids",
        "expected_date_range",
        "notes",
    }
    for line_number, row in load_jsonl_rows(EVAL_QUESTIONS_PATH):
        assert_required_fields(EVAL_QUESTIONS_PATH, line_number, row, eval_required)
        for field in {"id", "question", "category", "notes"}:
            assert_string_field(EVAL_QUESTIONS_PATH, line_number, row, field)
        for field in {"expected_topics", "expected_keywords"}:
            assert_string_list(EVAL_QUESTIONS_PATH, line_number, row, field)
        for field in {"expected_article_ids", "expected_chunk_ids"}:
            assert isinstance(row[field], list), (
                f"{EVAL_QUESTIONS_PATH}:{line_number} field {field!r} must be list"
            )
        date_range = row["expected_date_range"]
        assert isinstance(date_range, dict), (
            f"{EVAL_QUESTIONS_PATH}:{line_number} field 'expected_date_range' must be dict"
        )
        assert {"start", "end"} <= set(date_range), (
            f"{EVAL_QUESTIONS_PATH}:{line_number} expected_date_range must include start/end"
        )
        for bound in {"start", "end"}:
            assert date_range[bound] is None or isinstance(date_range[bound], str), (
                f"{EVAL_QUESTIONS_PATH}:{line_number} expected_date_range[{bound!r}] "
                "must be str or None"
            )

    golden_required = {
        "id",
        "question",
        "category",
        "expected_keywords",
        "expected_sources",
        "notes",
    }
    source_required = {"source_id", "article_id", "title", "url", "chunk_id"}
    for line_number, row in load_jsonl_rows(GOLDEN_QUESTIONS_PATH):
        assert_required_fields(GOLDEN_QUESTIONS_PATH, line_number, row, golden_required)
        for field in {"id", "question", "category", "notes"}:
            assert_string_field(GOLDEN_QUESTIONS_PATH, line_number, row, field)
        assert_string_list(GOLDEN_QUESTIONS_PATH, line_number, row, "expected_keywords")
        sources = row["expected_sources"]
        assert isinstance(sources, list), (
            f"{GOLDEN_QUESTIONS_PATH}:{line_number} field 'expected_sources' must be list"
        )
        assert sources, (
            f"{GOLDEN_QUESTIONS_PATH}:{line_number} field 'expected_sources' must not be empty"
        )
        for index, source in enumerate(sources):
            location = f"{GOLDEN_QUESTIONS_PATH}:{line_number} expected_sources[{index}]"
            assert isinstance(source, dict), f"{location} must be dict"
            assert_required_fields(GOLDEN_QUESTIONS_PATH, line_number, source, source_required)
            assert isinstance(source["article_id"], int), (
                f"{location} field 'article_id' must be int"
            )
            for field in source_required - {"article_id"}:
                assert_string_field(GOLDEN_QUESTIONS_PATH, line_number, source, field)
            assert source["source_id"] == str(source["article_id"]), (
                f"{location} source_id must match article_id"
            )
            assert source["chunk_id"].startswith(f"{source['article_id']}:"), (
                f"{location} chunk_id must start with '<article_id>:'"
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
