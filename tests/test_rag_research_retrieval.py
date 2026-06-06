import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run_rag_research_retrieval.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("run_rag_research_retrieval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def question_row(**overrides):
    row = {
        "question_id": "research_q_001",
        "question": "금리 상승은 주식시장에 어떤 부담으로 작용하는가?",
        "topic": "금리/긴축/주식시장",
        "source_refs": ["article_id:1001:chunk_id:1001:0"],
        "generated_from": ["chunk_keyword"],
        "db_only": True,
        "status": "candidate",
    }
    row.update(overrides)
    return row


def point(score: float = 0.58):
    return SimpleNamespace(
        score=score,
        payload={
            "chunk_id": "1001:0",
            "article_id": 1001,
            "title": "긴축은 주식시장의 악재",
            "text": "긴축은 할인율을 높이고 위험자산 선호를 약화시켜 주식시장에 부담을 준다.",
        },
    )


def test_find_latest_questions_file_uses_latest_report_timestamp(tmp_path):
    runner = load_runner()
    older = tmp_path / "rag-research-questions-20260601-010101.jsonl"
    newer = tmp_path / "rag-research-questions-20260601-020202.jsonl"
    write_jsonl(older, [question_row(question_id="research_q_001")])
    write_jsonl(newer, [question_row(question_id="research_q_002")])

    assert runner.find_latest_questions_file(tmp_path) == newer


def test_load_questions_preserves_db_only_fields_and_rejects_non_db_only(tmp_path):
    runner = load_runner()
    path = tmp_path / "questions.jsonl"
    write_jsonl(path, [question_row()])

    rows = runner.load_questions(path)

    assert rows[0]["question_id"] == "research_q_001"
    assert rows[0]["topic"] == "금리/긴축/주식시장"
    assert rows[0]["source_refs"] == ["article_id:1001:chunk_id:1001:0"]
    assert rows[0]["db_only"] is True

    write_jsonl(path, [question_row(db_only=False)])
    with pytest.raises(ValueError, match="db_only=true"):
        runner.load_questions(path)


def test_run_retrieval_structures_search_results_and_preserves_question_metadata():
    runner = load_runner()
    questions = [question_row()]

    def fake_embed(query, model, project_root):
        assert query == questions[0]["question"]
        assert model == "test-model"
        return np.ones(1024, dtype=np.float32)

    def fake_search(client, collection, query_vector, top_k):
        assert client == "client"
        assert collection == "collection"
        assert top_k == 5
        assert len(query_vector) == 1024
        return [point()]

    records = runner.run_retrieval(
        questions,
        client="client",
        collection="collection",
        model="test-model",
        top_k=5,
        embed_fn=fake_embed,
        search_fn=fake_search,
        project_root=ROOT,
    )

    assert records == [
        {
            "question_id": "research_q_001",
            "question": "금리 상승은 주식시장에 어떤 부담으로 작용하는가?",
            "topic": "금리/긴축/주식시장",
            "source_refs": ["article_id:1001:chunk_id:1001:0"],
            "generated_from": ["chunk_keyword"],
            "db_only": True,
            "top_k": 5,
            "results": [
                {
                    "rank": 1,
                    "chunk_id": "1001:0",
                    "article_id": 1001,
                    "title": "긴축은 주식시장의 악재",
                    "score": 0.58,
                    "source_ref": "article_id:1001:chunk_id:1001:0",
                    "text_preview": "긴축은 할인율을 높이고 위험자산 선호를 약화시켜 주식시장에 부담을 준다.",
                }
            ],
            "retrieval_status": "ok",
            "backend_status": "ok",
        }
    ]


def test_run_retrieval_marks_no_results():
    runner = load_runner()

    records = runner.run_retrieval(
        [question_row()],
        client="client",
        collection="collection",
        model="test-model",
        top_k=3,
        embed_fn=lambda query, model, project_root: np.ones(1024, dtype=np.float32),
        search_fn=lambda client, collection, query_vector, top_k: [],
        project_root=ROOT,
    )

    assert records[0]["results"] == []
    assert records[0]["retrieval_status"] == "no_results"
    assert records[0]["backend_status"] == "ok"


def test_check_backend_availability_distinguishes_missing_empty_and_ok():
    runner = load_runner()

    missing = runner.check_backend_availability(
        {"collection_exists": False},
        qdrant_path=Path("data/qdrant"),
        collection="goodmorning_chunks",
    )
    empty = runner.check_backend_availability(
        {"collection_exists": True, "points_count": 0},
        qdrant_path=Path("data/qdrant"),
        collection="goodmorning_chunks",
    )
    ok = runner.check_backend_availability(
        {"collection_exists": True, "points_count": 10},
        qdrant_path=Path("data/qdrant"),
        collection="goodmorning_chunks",
    )

    assert missing.backend_status == "unavailable"
    assert missing.backend_reason == "collection_missing: goodmorning_chunks"
    assert missing.can_search is False
    assert empty.backend_status == "empty_collection"
    assert "0 points" in empty.backend_reason
    assert empty.can_search is False
    assert ok.backend_status == "ok"
    assert ok.backend_reason == "collection_available"
    assert ok.can_search is True


def test_build_backend_unavailable_records_preserves_questions_and_backend_status():
    runner = load_runner()

    records = runner.build_backend_unavailable_records(
        [question_row()],
        top_k=5,
        backend_status="unavailable",
        backend_reason="collection_missing: goodmorning_chunks",
    )

    assert records[0]["question_id"] == "research_q_001"
    assert records[0]["source_refs"] == ["article_id:1001:chunk_id:1001:0"]
    assert records[0]["results"] == []
    assert records[0]["retrieval_status"] == "backend_unavailable"
    assert records[0]["backend_status"] == "unavailable"
    assert records[0]["backend_reason"] == "collection_missing: goodmorning_chunks"


def test_build_backend_unavailable_records_rejects_ok_status():
    runner = load_runner()

    with pytest.raises(ValueError, match="must not be ok"):
        runner.build_backend_unavailable_records(
            [question_row()],
            top_k=5,
            backend_status="ok",
            backend_reason="collection_available",
        )


def test_text_preview_is_limited_and_normalized():
    runner = load_runner()
    preview = runner.text_preview("a\n" + ("b" * 300), limit=20)

    assert preview == "a bbbbbbbbbbbbbbb..."
    assert len(preview) == 20
    assert "\n" not in preview


def test_format_markdown_report_is_human_readable():
    runner = load_runner()
    record = runner.build_retrieval_record(question_row(), runner.format_search_results([point()]), top_k=5)
    availability = runner.BackendAvailability(
        "ok",
        "collection_available",
        {"collection_exists": True, "points_count": 1},
    )

    markdown = runner.format_markdown_report(
        [record],
        questions_file=Path("agent_reports/questions.jsonl"),
        generated_at="20260601-010203",
        qdrant_path=Path("data/qdrant"),
        collection="goodmorning_chunks",
        model="voyage-3-large",
        availability=availability,
    )

    assert "# RAG Research Question Retrieval Report" in markdown
    assert "- db_only: true" in markdown
    assert "- backend_status: ok" in markdown
    assert "## Settings Alignment" in markdown
    assert "### research_q_001" in markdown
    assert "| rank | score | article_id | chunk_id | title | preview |" in markdown
    assert "긴축은 주식시장의 악재" in markdown


def test_format_markdown_report_marks_backend_unavailable_instead_of_no_results():
    runner = load_runner()
    availability = runner.BackendAvailability(
        "unavailable",
        "collection_missing: goodmorning_chunks",
        {"collection_exists": False},
    )
    records = runner.build_backend_unavailable_records(
        [question_row()],
        top_k=5,
        backend_status=availability.backend_status,
        backend_reason=availability.backend_reason,
    )

    markdown = runner.format_markdown_report(
        records,
        questions_file=Path("agent_reports/questions.jsonl"),
        generated_at="20260601-010203",
        qdrant_path=Path("data/qdrant"),
        collection="goodmorning_chunks",
        model="voyage-3-large",
        availability=availability,
    )

    assert "- backend_status: unavailable" in markdown
    assert "- backend_reason: collection_missing: goodmorning_chunks" in markdown
    assert "- retrieval_no_results: 0" in markdown
    assert "- retrieval_backend_unavailable: 1" in markdown
    assert "- status: backend_unavailable" in markdown
    assert "Retrieval backend unavailable: collection_missing: goodmorning_chunks" in markdown


def test_write_jsonl_uses_ascii_escapes_for_console_safe_reports(tmp_path):
    runner = load_runner()
    path = tmp_path / "retrieval.jsonl"

    runner.write_jsonl(path, [{"question": "금리 상승"}])

    raw = path.read_text(encoding="utf-8")
    assert "\\uae08\\ub9ac" in raw
    assert "금리" not in raw


def test_cli_help_runs_without_retrieval():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Run DB-only RAG retrieval" in result.stdout
