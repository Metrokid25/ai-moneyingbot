import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "prepare_manual_task_review.py"
DOCS = ROOT / "docs" / "rag_manual_task_review_gate.md"


def load_runner():
    spec = importlib.util.spec_from_file_location("prepare_manual_task_review", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_review_prompt_contains_pass_gated_push_rule_and_focused_validation():
    runner = load_runner()

    prompt = runner.render_review_prompt(
        "058-rag-manual-task-review-gate",
        "Manual RAG task review gate",
    )

    assert "Do not push this task until an independent Codex reviewer returns PASS." in prompt
    assert "FAIL, NEEDS_HUMAN_REVIEW, empty, or ambiguous" in prompt
    assert "python scripts/run_rag_focused_tests.py" in prompt
    assert "Full pytest is not the default manual RAG task gate." in prompt
    assert "git diff --check" in prompt
    assert "git status -sb" in prompt
    assert "Do not implement; review only." in prompt
    assert "Reviewer must not modify files, commit, or push." in prompt


def test_review_prompt_keeps_rag_scope_and_archive_owned_task_guard():
    runner = load_runner()

    prompt = runner.render_review_prompt("058-rag-manual-task-review-gate")

    assert ".env" in prompt
    assert "archive.db" in prompt
    assert "data/" in prompt
    assert "scripts/daily_archive.py" in prompt
    assert "src/collector.py" in prompt
    assert "Trading Bot related files" in prompt
    assert "Do not access Naver Cafe." in prompt
    assert "001-real-daily-archive-wiring.md" in prompt
    assert "must remain unimplemented by the RAG Bot" in prompt


def test_archive_owned_task_ref_is_marked_blocked_for_rag_implementation():
    runner = load_runner()

    prompt = runner.render_review_prompt("agent_tasks/pending/001-real-daily-archive-wiring.md")

    assert runner.is_archive_owned_task("001-real-daily-archive-wiring.md")
    assert "BLOCKED FOR RAG IMPLEMENTATION" in prompt
    assert "001-real-daily-archive-wiring.md" in prompt
    assert "Archive-owned task" in prompt
    assert "RAG Bot must not implement this task" in prompt


def test_archive_owned_task_detection_accepts_id_filename_and_paths():
    runner = load_runner()

    archive_refs = [
        "001-real-daily-archive-wiring",
        "001-real-daily-archive-wiring.md",
        "agent_tasks/pending/001-real-daily-archive-wiring.md",
        r"agent_tasks\pending\001-real-daily-archive-wiring.md",
        "  agent_tasks/pending/001-real-daily-archive-wiring.md  ",
    ]

    for task_ref in archive_refs:
        prompt = runner.render_review_prompt(task_ref)
        assert runner.is_archive_owned_task(task_ref)
        assert "BLOCKED FOR RAG IMPLEMENTATION" in prompt
        assert "001-real-daily-archive-wiring.md" in prompt
        assert "Archive-owned task" in prompt
        assert "RAG Bot must not implement this task" in prompt


def test_regular_rag_task_is_not_marked_blocked():
    runner = load_runner()

    prompt = runner.render_review_prompt("058-rag-manual-task-review-gate")

    assert not runner.is_archive_owned_task("058-rag-manual-task-review-gate")
    assert "BLOCKED FOR RAG IMPLEMENTATION" not in prompt
    assert "Archive-owned task guard" in prompt


def test_write_report_uses_task_slug_and_timestamp(tmp_path):
    runner = load_runner()
    content = runner.render_review_prompt("058-rag-manual-task-review-gate")

    path = runner.write_report(tmp_path, "058-rag-manual-task-review-gate", "20260610-101010", content)

    assert path.name == "rag-manual-task-review-20260610-101010-058-rag-manual-task-review-gate.md"
    assert path.read_text(encoding="utf-8") == content


def test_cli_help_and_stdout_prompt():
    help_result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "Prepare a PASS-gated review prompt" in help_result.stdout

    prompt_result = subprocess.run(
        [sys.executable, str(SCRIPT), "058-rag-manual-task-review-gate"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert prompt_result.returncode == 0
    assert "# Manual RAG Task Review Gate" in prompt_result.stdout
    assert "A push is allowed only for PASS." in prompt_result.stdout
    assert "Do not implement; review only." in prompt_result.stdout


def test_manual_review_gate_docs_match_operational_rules():
    docs = DOCS.read_text(encoding="utf-8")

    assert "python scripts/prepare_manual_task_review.py" in docs
    assert "Do not push until the independent reviewer returns `PASS`." in docs
    assert "python scripts/run_rag_focused_tests.py" in docs
    assert "Full pytest is not the default requirement" in docs
    assert "001-real-daily-archive-wiring.md" in docs
    assert "The RAG Bot must not implement it." in docs
    assert "The reviewer must review only." in docs
    assert "must not implement additional changes, modify files, create commits, or push" in docs
    assert "Trading Bot related files" in docs
