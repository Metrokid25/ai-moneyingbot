import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run_rag_research_learning_loop.py"
DOC = ROOT / "docs" / "rag_autonomous_learning_loop.md"


def load_runner():
    spec = importlib.util.spec_from_file_location("run_rag_research_learning_loop", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def normalized_command(argv) -> tuple[str, ...]:
    return tuple(str(part).replace("\\", "/") for part in argv)


def retrieval_row(question_id: str, status: str = "ok", backend_status: str = "ok") -> dict:
    results = []
    if status == "ok":
        results = [
            {
                "rank": 1,
                "article_id": 1001,
                "chunk_id": "1001:0",
                "title": "DB evidence one",
                "score": 0.61,
                "source_ref": "article_id:1001:chunk_id:1001:0",
                "text_preview": f"{question_id} uses DB evidence for the first grounded learning signal.",
            },
            {
                "rank": 2,
                "article_id": 1002,
                "chunk_id": "1002:0",
                "title": "DB evidence two",
                "score": 0.58,
                "source_ref": "article_id:1002:chunk_id:1002:0",
                "text_preview": f"{question_id} keeps the answer limited to stored database evidence.",
            },
        ]
    return {
        "question_id": question_id,
        "question": f"What should the DB evidence say about {question_id}?",
        "db_only": True,
        "retrieval_status": status,
        "backend_status": backend_status,
        "results": results,
    }


def answer_row(question_id: str, status: str) -> dict:
    return {
        "question_id": question_id,
        "question": f"What should the answer say about {question_id}?",
        "db_only": True,
        "answer_status": status,
        "answer": "",
    }


def test_questions_file_plan_runs_retrieval_then_answer():
    runner = load_runner()
    args = SimpleNamespace(
        questions_file=Path("agent_reports/questions.jsonl"),
        retrieval_file=None,
        qdrant_path=Path(".qdrant"),
        collection="goodmorning_chunks",
        top_k=7,
        out_dir=Path("agent_reports"),
    )

    plan = runner.build_learning_plan(args, "20260610-010203")
    retrieval_command = normalized_command(plan.retrieval_command)
    answer_command = normalized_command(plan.answer_command)

    assert plan.retrieval_command is not None
    assert "scripts/run_rag_research_retrieval.py" in retrieval_command
    assert "--questions-file" in retrieval_command
    assert "agent_reports/questions.jsonl" in retrieval_command
    assert "--qdrant-path" in retrieval_command
    assert "scripts/run_rag_research_answers.py" in answer_command
    assert "<retrieval report from previous step>" in answer_command


def test_retrieval_file_plan_skips_retrieval():
    runner = load_runner()
    args = SimpleNamespace(
        questions_file=None,
        retrieval_file=Path("agent_reports/retrieval.jsonl"),
        qdrant_path=None,
        collection="goodmorning_chunks",
        top_k=5,
        out_dir=Path("agent_reports"),
    )

    plan = runner.build_learning_plan(args, "20260610-010203")
    answer_command = normalized_command(plan.answer_command)

    assert plan.retrieval_command is None
    assert plan.retrieval_file == Path("agent_reports/retrieval.jsonl")
    assert "agent_reports/retrieval.jsonl" in answer_command


def test_summary_counts_answer_statuses_and_candidates(tmp_path):
    runner = load_runner()
    retrieval_path = tmp_path / "retrieval.jsonl"
    answer_path = tmp_path / "answers.jsonl"
    retrieval_records = [
        retrieval_row("research_q_001", "ok"),
        retrieval_row("research_q_002", "ok"),
        retrieval_row("research_q_003", "no_results"),
    ]
    answer_records = [
        answer_row("research_q_001", "ok"),
        answer_row("research_q_002", "weak_evidence"),
        answer_row("research_q_003", "no_evidence"),
    ]

    summary = runner.summarize_learning_loop(
        questions_file=tmp_path / "questions.jsonl",
        retrieval_file=retrieval_path,
        answer_file=answer_path,
        retrieval_records=retrieval_records,
        answer_records=answer_records,
        generated_at="20260610-010203",
    )

    assert summary["question_count"] == 3
    assert summary["retrieval_ok"] == 2
    assert summary["retrieval_no_results"] == 1
    assert summary["answer_ok"] == 1
    assert summary["answer_weak_evidence"] == 1
    assert summary["answer_no_evidence"] == 1
    assert summary["weak_evidence_question_ids"] == ["research_q_002"]
    assert summary["no_evidence_question_ids"] == ["research_q_003"]
    assert {"question_id": "research_q_002", "action": "needs_better_evidence"} in summary["next_learning_candidates"]
    assert {"question_id": "research_q_003", "action": "needs_retrieval_query_refinement"} in summary["next_learning_candidates"]
    assert {"question_id": "research_q_001", "action": "candidate_for_memory_store"} in summary["next_learning_candidates"]


def test_backend_unavailable_creates_backend_fix_candidate(tmp_path):
    runner = load_runner()
    summary = runner.summarize_learning_loop(
        questions_file=None,
        retrieval_file=tmp_path / "retrieval.jsonl",
        answer_file=tmp_path / "answers.jsonl",
        retrieval_records=[retrieval_row("research_q_004", "backend_unavailable", "unavailable")],
        answer_records=[answer_row("research_q_004", "backend_unavailable")],
        generated_at="20260610-010203",
    )

    assert summary["backend_unavailable"] is True
    assert summary["backend_status"] == "backend_unavailable"
    assert summary["retrieval_backend_unavailable"] == 1
    assert summary["answer_backend_unavailable"] == 1
    assert {
        "question_id": "research_q_004",
        "action": "fix_retrieval_backend_before_learning",
    } in summary["next_learning_candidates"]


def test_write_reports_persists_json_and_markdown(tmp_path):
    runner = load_runner()
    summary = {
        "generated_at": "20260610-010203",
        "db_only": True,
        "questions_file": "questions.jsonl",
        "retrieval_file": "retrieval.jsonl",
        "answer_file": "answers.jsonl",
        "backend_status": "ok",
        "question_count": 1,
        "retrieval_ok": 1,
        "retrieval_no_results": 0,
        "retrieval_backend_unavailable": 0,
        "answer_ok": 1,
        "answer_weak_evidence": 0,
        "answer_no_evidence": 0,
        "answer_backend_unavailable": 0,
        "weak_evidence_question_ids": [],
        "no_evidence_question_ids": [],
        "backend_unavailable": False,
        "next_learning_candidates": [{"question_id": "research_q_001", "action": "candidate_for_memory_store"}],
        "next_actions": ["candidate_for_memory_store"],
    }

    json_path, md_path = runner.write_reports(tmp_path, "20260610-010203", summary)

    assert json_path.name == "rag-learning-loop-20260610-010203.json"
    assert md_path.name == "rag-learning-loop-20260610-010203.md"
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["answer_ok"] == 1
    markdown = md_path.read_text(encoding="utf-8")
    assert "# RAG Autonomous Research Learning Loop Report" in markdown
    assert "DB-only Safety" in markdown
    assert "candidate_for_memory_store" in markdown


def test_cli_with_retrieval_file_writes_learning_reports(tmp_path):
    retrieval_path = tmp_path / "retrieval.jsonl"
    answer_path = tmp_path / "answers" / "rag-research-answers-20260610-010203.jsonl"
    write_jsonl(retrieval_path, [retrieval_row("research_q_001", "ok")])
    write_jsonl(answer_path, [answer_row("research_q_001", "ok")])

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--retrieval-file",
            str(retrieval_path),
            "--out-dir",
            str(tmp_path),
            "--timestamp",
            "20260610-010203",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    summary_path = tmp_path / "rag-learning-loop-20260610-010203.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["retrieval_file"] == str(retrieval_path)
    assert summary["answer_ok"] == 1
    assert "RAG DB-only research learning loop completed" in result.stdout


def test_cli_update_memory_store_is_opt_in(tmp_path):
    retrieval_path = tmp_path / "retrieval.jsonl"
    write_jsonl(retrieval_path, [retrieval_row("research_q_001", "ok")])
    store_path = tmp_path / "memory.jsonl"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--retrieval-file",
            str(retrieval_path),
            "--out-dir",
            str(tmp_path),
            "--memory-store-file",
            str(store_path),
            "--timestamp",
            "20260610-010203",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not store_path.exists()

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--retrieval-file",
            str(retrieval_path),
            "--out-dir",
            str(tmp_path),
            "--update-memory-store",
            "--memory-store-file",
            str(store_path),
            "--timestamp",
            "20260610-010204",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert store_path.exists()
    assert "Memory added: 1" in result.stdout


def test_help_and_docs_include_db_only_safety_language():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    help_text = result.stdout
    doc_text = DOC.read_text(encoding="utf-8")
    assert "--update-memory-store" in help_text
    assert "--memory-store-file" in help_text
    for text in (help_text, doc_text):
        assert "DB-only" in text
        assert "external web" in text
        assert "current market" in text
        assert "Naver Cafe" in text
        assert "archive writes" in text


def test_script_does_not_call_external_web_or_archive_write_code():
    source = SCRIPT.read_text(encoding="utf-8")

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
    ]
    for fragment in forbidden_fragments:
        assert fragment not in source
