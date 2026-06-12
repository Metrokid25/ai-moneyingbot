import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "update_rag_research_memory_store.py"
LEARNING_SCRIPT = ROOT / "scripts" / "run_rag_research_learning_loop.py"
DOC = ROOT / "docs" / "rag_research_memory_store.md"


def load_updater():
    spec = importlib.util.spec_from_file_location("update_rag_research_memory_store", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def answer_row(question_id: str, status: str = "ok", answer: str | None = None) -> dict:
    return {
        "question_id": question_id,
        "question": f"What does DB evidence say about {question_id}?",
        "topic": "research",
        "db_only": True,
        "answer_status": status,
        "answer": answer or f"DB evidence supports a reusable answer for {question_id}.",
        "used_sources": [
            {
                "rank": 1,
                "article_id": 1001,
                "chunk_id": "1001:0",
                "title": "Stored DB article",
                "source_ref": f"article_id:1001:chunk_id:{question_id}",
            }
        ],
    }


def write_learning_summary(path: Path, answer_file: Path, candidates: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at": "20260612-010203",
        "db_only": True,
        "retrieval_file": str(path.parent / "retrieval.jsonl"),
        "answer_file": str(answer_file),
        "next_learning_candidates": [
            {"question_id": question_id, "action": "candidate_for_memory_store"}
            for question_id in (candidates or [])
        ],
    }
    path.write_text(json.dumps(summary, ensure_ascii=True), encoding="utf-8")


def test_answer_ok_is_saved_as_memory_record(tmp_path):
    updater = load_updater()
    answer_file = tmp_path / "answers.jsonl"
    learning_file = tmp_path / "learning.json"
    store_file = tmp_path / "memory.jsonl"
    write_jsonl(answer_file, [answer_row("research_q_001", "ok")])
    write_learning_summary(learning_file, answer_file)

    summary, _json_path, _md_path = updater.update_memory_store(
        learning_loop_file=learning_file,
        out_file=store_file,
        timestamp="20260612-010203",
    )

    rows = read_jsonl(store_file)
    assert summary["candidate_count"] == 1
    assert summary["added_count"] == 1
    assert len(rows) == 1
    record = rows[0]
    assert record["memory_id"].startswith("ragmem_")
    assert record["question_id"] == "research_q_001"
    assert record["answer_status"] == "ok"
    assert record["evidence_strength"] == "db_grounded"
    assert record["source_refs"] == ["article_id:1001:chunk_id:research_q_001"]
    assert record["promotion_status"] == "pending_human_review"


def test_candidate_for_memory_store_from_learning_summary_is_saved(tmp_path):
    updater = load_updater()
    answer_file = tmp_path / "answers.jsonl"
    learning_file = tmp_path / "learning.json"
    store_file = tmp_path / "memory.jsonl"
    write_jsonl(answer_file, [answer_row("research_q_002", "weak_evidence")])
    write_learning_summary(learning_file, answer_file, candidates=["research_q_002"])

    summary, _json_path, _md_path = updater.update_memory_store(
        learning_loop_file=learning_file,
        out_file=store_file,
        timestamp="20260612-010203",
    )

    rows = read_jsonl(store_file)
    assert summary["candidate_count"] == 1
    assert summary["added_count"] == 1
    assert rows[0]["question_id"] == "research_q_002"


def test_weak_no_evidence_and_backend_unavailable_are_excluded_by_default(tmp_path):
    updater = load_updater()
    answer_file = tmp_path / "answers.jsonl"
    learning_file = tmp_path / "learning.json"
    store_file = tmp_path / "memory.jsonl"
    write_jsonl(
        answer_file,
        [
            answer_row("research_q_003", "weak_evidence"),
            answer_row("research_q_004", "no_evidence"),
            answer_row("research_q_005", "backend_unavailable"),
        ],
    )
    write_learning_summary(learning_file, answer_file)

    summary, _json_path, _md_path = updater.update_memory_store(
        learning_loop_file=learning_file,
        out_file=store_file,
        timestamp="20260612-010203",
    )

    assert summary["candidate_count"] == 0
    assert summary["added_count"] == 0
    assert summary["skipped_non_ok_count"] == 3
    assert not store_file.exists()


def test_same_input_is_idempotent_and_skips_duplicate(tmp_path):
    updater = load_updater()
    answer_file = tmp_path / "answers.jsonl"
    learning_file = tmp_path / "learning.json"
    store_file = tmp_path / "memory.jsonl"
    write_jsonl(answer_file, [answer_row("research_q_006", "ok")])
    write_learning_summary(learning_file, answer_file)

    first, _json_path, _md_path = updater.update_memory_store(
        learning_loop_file=learning_file,
        out_file=store_file,
        timestamp="20260612-010203",
    )
    second, _json_path, _md_path = updater.update_memory_store(
        learning_loop_file=learning_file,
        out_file=store_file,
        timestamp="20260612-010204",
    )

    assert first["added_count"] == 1
    assert second["added_count"] == 0
    assert second["skipped_duplicate_count"] == 1
    assert len(read_jsonl(store_file)) == 1


def test_dry_run_does_not_write_memory_store_but_writes_summary(tmp_path):
    updater = load_updater()
    answer_file = tmp_path / "answers.jsonl"
    learning_file = tmp_path / "learning.json"
    store_file = tmp_path / "memory.jsonl"
    write_jsonl(answer_file, [answer_row("research_q_007", "ok")])
    write_learning_summary(learning_file, answer_file)

    summary, json_path, md_path = updater.update_memory_store(
        learning_loop_file=learning_file,
        out_file=store_file,
        dry_run=True,
        timestamp="20260612-010203",
    )

    assert summary["dry_run"] is True
    assert summary["added_count"] == 1
    assert not store_file.exists()
    assert json_path.exists()
    assert md_path.exists()


def test_summary_report_includes_added_and_skipped_counts(tmp_path):
    updater = load_updater()
    answer_file = tmp_path / "answers.jsonl"
    learning_file = tmp_path / "learning.json"
    store_file = tmp_path / "memory.jsonl"
    write_jsonl(answer_file, [answer_row("research_q_008", "ok"), answer_row("research_q_009", "no_evidence")])
    write_learning_summary(learning_file, answer_file)

    summary, json_path, md_path = updater.update_memory_store(
        learning_loop_file=learning_file,
        out_file=store_file,
        timestamp="20260612-010203",
    )

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")
    assert summary["added_count"] == 1
    assert saved["added_count"] == 1
    assert saved["skipped_non_ok_count"] == 1
    assert "- added_count: 1" in markdown
    assert "- skipped_non_ok_count: 1" in markdown


def test_learning_loop_json_answer_file_is_used_when_answer_file_is_omitted(tmp_path):
    updater = load_updater()
    answer_file = tmp_path / "answers-from-learning.jsonl"
    learning_file = tmp_path / "learning.json"
    store_file = tmp_path / "memory.jsonl"
    write_jsonl(answer_file, [answer_row("research_q_010", "ok")])
    write_learning_summary(learning_file, answer_file)

    summary, _json_path, _md_path = updater.update_memory_store(
        learning_loop_file=learning_file,
        out_file=store_file,
        timestamp="20260612-010203",
    )

    assert summary["answer_file"] == str(answer_file)
    assert read_jsonl(store_file)[0]["question_id"] == "research_q_010"


def test_explicit_answer_file_overrides_learning_loop_answer_file(tmp_path):
    updater = load_updater()
    learning_answer_file = tmp_path / "answers-from-learning.jsonl"
    explicit_answer_file = tmp_path / "answers-explicit.jsonl"
    learning_file = tmp_path / "learning.json"
    store_file = tmp_path / "memory.jsonl"
    write_jsonl(learning_answer_file, [answer_row("research_q_011", "no_evidence")])
    write_jsonl(explicit_answer_file, [answer_row("research_q_012", "ok")])
    write_learning_summary(learning_file, learning_answer_file)

    summary, _json_path, _md_path = updater.update_memory_store(
        learning_loop_file=learning_file,
        answer_file=explicit_answer_file,
        out_file=store_file,
        timestamp="20260612-010203",
    )

    assert summary["answer_file"] == str(explicit_answer_file)
    assert read_jsonl(store_file)[0]["question_id"] == "research_q_012"


def test_db_only_language_is_in_help_docs_and_report(tmp_path):
    updater = load_updater()
    answer_file = tmp_path / "answers.jsonl"
    learning_file = tmp_path / "learning.json"
    store_file = tmp_path / "memory.jsonl"
    write_jsonl(answer_file, [answer_row("research_q_013", "ok")])
    write_learning_summary(learning_file, answer_file)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    _summary, json_path, _md_path = updater.update_memory_store(
        learning_loop_file=learning_file,
        out_file=store_file,
        timestamp="20260612-010203",
    )

    help_text = result.stdout
    doc_text = DOC.read_text(encoding="utf-8")
    report_text = json_path.read_text(encoding="utf-8")
    for text in (help_text, doc_text, report_text):
        assert "DB-only" in text
        assert "external web" in text
        assert "Naver Cafe" in text
        assert "archive writes" in text
        assert "Trading Bot" in text


def test_no_external_or_archive_or_trading_calls_are_added():
    update_source = SCRIPT.read_text(encoding="utf-8")
    learning_source = LEARNING_SCRIPT.read_text(encoding="utf-8")
    combined = update_source + "\n" + learning_source

    forbidden_fragments = [
        "requests.",
        "urllib",
        "http://",
        "https://",
        "daily_archive.py",
        "batch_recollect.py",
        "index_tail.py",
        "collector.py",
        "browser.py",
        "parser.py",
        "trading_bot",
        "TradingBot",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in combined
    assert "subprocess.run" not in update_source
