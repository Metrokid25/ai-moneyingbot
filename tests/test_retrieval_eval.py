import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_retrieval import (
    EVALUATION_QUERIES,
    build_eval_record,
    validate_eval_queries,
    validate_output_path,
    validate_run_mode,
    validate_top_k,
    write_jsonl,
)


def test_evaluation_query_set_has_15_queries():
    validate_eval_queries(EVALUATION_QUERIES)

    assert len(EVALUATION_QUERIES) == 15


def test_validate_eval_queries_rejects_empty_list():
    with pytest.raises(ValueError, match="must not be empty"):
        validate_eval_queries([])


def test_validate_eval_queries_rejects_empty_query():
    with pytest.raises(ValueError, match="empty values"):
        validate_eval_queries(["valid query", "  "])


def test_validate_eval_queries_rejects_duplicate_query():
    with pytest.raises(ValueError, match="duplicates"):
        validate_eval_queries(["same", "same"])


def test_build_eval_record_shape_and_snippet_limit():
    result = {
        "rank": 1,
        "score": 0.7,
        "chunk_id": "1:0",
        "article_id": 1,
        "posted_at": "2026.05.19.",
        "title": "title",
        "snippet": "x" * 300,
        "source": "source",
    }

    record = build_eval_record("query", [result], top_k=5)

    assert record["query"] == "query"
    assert record["top_k"] == 5
    assert len(record["results"]) == 1
    assert record["results"][0]["rank"] == 1
    assert len(record["results"][0]["snippet"]) == 250


def test_top_k_range_validation_for_eval():
    validate_top_k(1)
    validate_top_k(20)
    with pytest.raises(ValueError, match="--top-k"):
        validate_top_k(0)
    with pytest.raises(ValueError, match="--top-k"):
        validate_top_k(21)


def test_dry_run_and_execute_are_mutually_exclusive():
    with pytest.raises(ValueError, match="mutually exclusive"):
        validate_run_mode(dry_run=True, execute=True)


def test_overwrite_requires_execute(tmp_path):
    out_path = tmp_path / "out.jsonl"

    with pytest.raises(ValueError, match="--overwrite requires --execute"):
        validate_output_path(out_path, overwrite=True, execute=False)


def test_existing_output_without_overwrite_fails(tmp_path):
    out_path = tmp_path / "out.jsonl"
    out_path.write_text("existing\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        validate_output_path(out_path, overwrite=False, execute=True)


def test_write_jsonl_writes_one_record_per_line(tmp_path):
    out_path = tmp_path / "out.jsonl"
    records = [
        build_eval_record("query 1", [], top_k=5),
        build_eval_record("query 2", [], top_k=5),
    ]

    write_jsonl(out_path, records)

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["query"] == "query 1"
    assert json.loads(lines[1])["query"] == "query 2"
