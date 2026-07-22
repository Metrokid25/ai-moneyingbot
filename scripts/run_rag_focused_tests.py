from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from os import getpid
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTEST_BASETEMP = ".tmp/rag_focused_pytest"
PYTEST_RUNTIME_BASETEMP_ROOT = ".tmp/rag_focused_pytest_runs"


def focused_pytest_basetemp() -> str:
    run_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"{PYTEST_RUNTIME_BASETEMP_ROOT}/run-{run_id}-{getpid()}"

FOCUSED_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "python scripts/answer_question_phase2.py --help",
        (sys.executable, "scripts/answer_question_phase2.py", "--help"),
    ),
    (
        "python scripts/report_rag_chunk_quality.py --help",
        (sys.executable, "scripts/report_rag_chunk_quality.py", "--help"),
    ),
    (
        "python scripts/generate_rag_research_questions.py --help",
        (sys.executable, "scripts/generate_rag_research_questions.py", "--help"),
    ),
    (
        "python scripts/run_rag_research_retrieval.py --help",
        (sys.executable, "scripts/run_rag_research_retrieval.py", "--help"),
    ),
    (
        "python scripts/run_rag_research_answers.py --help",
        (sys.executable, "scripts/run_rag_research_answers.py", "--help"),
    ),
    (
        "python scripts/run_rag_research_learning_loop.py --help",
        (sys.executable, "scripts/run_rag_research_learning_loop.py", "--help"),
    ),
    (
        "python scripts/update_rag_research_memory_store.py --help",
        (sys.executable, "scripts/update_rag_research_memory_store.py", "--help"),
    ),
    (
        "python scripts/prepare_rag_memory_promotion_review.py --help",
        (sys.executable, "scripts/prepare_rag_memory_promotion_review.py", "--help"),
    ),
    (
        "python scripts/update_rag_memory_promotion_status.py --help",
        (sys.executable, "scripts/update_rag_memory_promotion_status.py", "--help"),
    ),
    (
        "python scripts/preview_rag_approved_memory_export.py --help",
        (sys.executable, "scripts/preview_rag_approved_memory_export.py", "--help"),
    ),
    (
        "python scripts/draft_rag_approved_memory_rule_candidates.py --help",
        (sys.executable, "scripts/draft_rag_approved_memory_rule_candidates.py", "--help"),
    ),
    (
        "python scripts/validate_rag_rule_candidate_drafts.py --help",
        (sys.executable, "scripts/validate_rag_rule_candidate_drafts.py", "--help"),
    ),
    (
        "python scripts/update_rag_rule_candidate_registry.py --help",
        (sys.executable, "scripts/update_rag_rule_candidate_registry.py", "--help"),
    ),
    (
        "python scripts/preview_rag_trading_rule_export.py --help",
        (sys.executable, "scripts/preview_rag_trading_rule_export.py", "--help"),
    ),
    (
        "python scripts/run_rag_end_to_end_runtime_smoke.py --help",
        (sys.executable, "scripts/run_rag_end_to_end_runtime_smoke.py", "--help"),
    ),
    (
        "python scripts/prepare_manual_task_review.py --help",
        (sys.executable, "scripts/prepare_manual_task_review.py", "--help"),
    ),
    (
        f"pytest tests/test_rag_answering.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_answering.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_answer_context.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_answer_context.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_web.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_web.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_ingest_archive_export.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_ingest_archive_export.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_chunking.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_chunking.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_fixture_jsonl_smoke.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_fixture_jsonl_smoke.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_chunk_quality_report.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_chunk_quality_report.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_fixture_retrieval_eval.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_fixture_retrieval_eval.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_retrieval_eval.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_retrieval_eval.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_eval_questions.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_eval_questions.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_retrieval_eval_set.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_retrieval_eval_set.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_golden_questions.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_golden_questions.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_retrieval.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_retrieval.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_rerank.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_rerank.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_retrieve_rerank.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_retrieve_rerank.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_retrieval_regression.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_retrieval_regression.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_answer_citation_contract.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_answer_citation_contract.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_source_metadata_normalization.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_source_metadata_normalization.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_no_context_answer_contract.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_no_context_answer_contract.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_answer_grounding_eval.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_answer_grounding_eval.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_qdrant.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_qdrant.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_check_rag_deploy_assets.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_check_rag_deploy_assets.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_run_rag_incremental_notify.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_run_rag_incremental_notify.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_agent_next_task.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_agent_next_task.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_autorunner_docs.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_autorunner_docs.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_review_pipeline.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_review_pipeline.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_autonomous_loop.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_autonomous_loop.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_planner.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_planner.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_focused_tests.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_focused_tests.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_research_questions.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_research_questions.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_research_retrieval.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_research_retrieval.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_research_answers.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_research_answers.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_research_learning_loop.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_research_learning_loop.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_research_memory_store.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_research_memory_store.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_memory_promotion_gate.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_memory_promotion_gate.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_approved_memory_export_preview.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_approved_memory_export_preview.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_approved_memory_rule_candidate_draft.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_approved_memory_rule_candidate_draft.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_rule_candidate_schema.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_rule_candidate_schema.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_rule_candidate_registry.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_rule_candidate_registry.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_trading_export_preview.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_trading_export_preview.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_end_to_end_runtime_smoke.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_end_to_end_runtime_smoke.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_manual_task_review_gate.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_manual_task_review_gate.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_operator_runbook_docs.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_operator_runbook_docs.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_verify_runner.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_verify_runner.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_archive_export.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_archive_export.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_incremental_update.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_incremental_update.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
)


def run_command(display: str, argv: Sequence[str]) -> int:
    print(f"$ {display}", flush=True)
    prepare_pytest_basetemp_parent(argv)
    result = subprocess.run(argv, cwd=PROJECT_ROOT, check=False)
    return int(result.returncode)


def prepare_pytest_basetemp_parent(argv: Sequence[str]) -> None:
    for arg in argv:
        if arg.startswith("--basetemp="):
            basetemp = Path(arg.removeprefix("--basetemp="))
            (PROJECT_ROOT / basetemp).parent.mkdir(parents=True, exist_ok=True)
            return


def runtime_focused_commands(pytest_basetemp: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    commands: list[tuple[str, tuple[str, ...]]] = []
    pytest_index = 0
    for display, argv in FOCUSED_COMMANDS:
        command_basetemp = pytest_basetemp
        if argv and argv[0] == "pytest":
            pytest_index += 1
            command_basetemp = f"{pytest_basetemp}/cmd-{pytest_index:02d}"
        runtime_display = display.replace(PYTEST_BASETEMP, command_basetemp)
        runtime_argv = tuple(arg.replace(PYTEST_BASETEMP, command_basetemp) for arg in argv)
        commands.append((runtime_display, runtime_argv))
    return tuple(commands)


def main() -> int:
    (PROJECT_ROOT / PYTEST_RUNTIME_BASETEMP_ROOT).mkdir(parents=True, exist_ok=True)
    for display, argv in runtime_focused_commands(focused_pytest_basetemp()):
        exit_code = run_command(display, argv)
        if exit_code != 0:
            print(f"FAILED: {display} exited with {exit_code}", file=sys.stderr)
            return exit_code
    print("RAG focused test suite passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
