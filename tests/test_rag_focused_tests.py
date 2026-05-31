import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run_rag_focused_tests.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("run_rag_focused_tests", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_focused_runner_uses_only_explicit_rag_commands():
    runner = load_runner()
    displays = [display for display, _argv in runner.FOCUSED_COMMANDS]

    assert displays == [
        "python scripts/answer_question_phase2.py --help",
        "python scripts/report_rag_chunk_quality.py --help",
        "pytest tests/test_rag_answering.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_answer_context.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_web.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_ingest_archive_export.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_chunking.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_fixture_jsonl_smoke.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_chunk_quality_report.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_fixture_retrieval_eval.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_retrieval_eval.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_eval_questions.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_retrieval_eval_set.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_golden_questions.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_retrieval.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_retrieval_regression.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_answer_citation_contract.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_source_metadata_normalization.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_no_context_answer_contract.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_answer_grounding_eval.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_qdrant.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_agent_next_task.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_autorunner_docs.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_review_pipeline.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_autonomous_loop.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_planner.py --basetemp=.tmp/rag_focused_pytest",
        "pytest tests/test_rag_focused_tests.py --basetemp=.tmp/rag_focused_pytest",
    ]
    assert all(display != "pytest" for display in displays)
    assert all("pytest --basetemp" not in display for display in displays)


def test_focused_runner_includes_current_rag_test_files():
    runner = load_runner()
    command_tests = {
        argv[1].replace("\\", "/")
        for _display, argv in runner.FOCUSED_COMMANDS
        if argv and argv[0] == "pytest"
    }
    rag_test_files = {
        f"tests/{path.name}"
        for path in (ROOT / "tests").glob("test_rag_*.py")
    }

    assert rag_test_files <= command_tests
    assert "tests/test_ingest_archive_export.py" in command_tests
    assert "tests/test_retrieval_eval.py" in command_tests


def test_focused_runner_stops_on_first_failure(monkeypatch):
    runner = load_runner()
    calls = []

    def fake_run_command(display, argv):
        calls.append((display, argv))
        return 7

    monkeypatch.setattr(runner, "run_command", fake_run_command)

    assert runner.main() == 7
    assert len(calls) == 1
