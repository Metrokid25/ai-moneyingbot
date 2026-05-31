from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTEST_BASETEMP = ".tmp/rag_focused_pytest"

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
        f"pytest tests/test_rag_answering.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_answering.py", f"--basetemp={PYTEST_BASETEMP}"),
    ),
    (
        f"pytest tests/test_rag_web.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_web.py", f"--basetemp={PYTEST_BASETEMP}"),
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
        f"pytest tests/test_rag_golden_questions.py --basetemp={PYTEST_BASETEMP}",
        ("pytest", "tests/test_rag_golden_questions.py", f"--basetemp={PYTEST_BASETEMP}"),
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
)


def run_command(display: str, argv: Sequence[str]) -> int:
    print(f"$ {display}", flush=True)
    result = subprocess.run(argv, cwd=PROJECT_ROOT, check=False)
    return int(result.returncode)


def main() -> int:
    (PROJECT_ROOT / ".tmp").mkdir(exist_ok=True)
    for display, argv in FOCUSED_COMMANDS:
        exit_code = run_command(display, argv)
        if exit_code != 0:
            print(f"FAILED: {display} exited with {exit_code}", file=sys.stderr)
            return exit_code
    print("RAG focused test suite passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
