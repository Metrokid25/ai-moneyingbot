from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNNER = "scripts/run_rag_verify.ps1"
DOC = "docs/rag_one_command_runner.md"


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_verify_runner_and_doc_exist():
    assert (ROOT / RUNNER).exists()
    assert (ROOT / DOC).exists()


def test_runner_declares_expected_parameters():
    script = read_text(RUNNER)

    for param in ("$Help", "$SmokeOnly", "$KeepArtifacts", "$WorkDir"):
        assert param in script


def test_runner_uses_venv_python():
    script = read_text(RUNNER)

    assert ".venv\\Scripts\\python.exe" in script
    # Must not fall back to a bare system python invocation for the steps.
    assert "& $VenvPython" in script


def test_runner_invokes_smoke_and_focused_suite():
    script = read_text(RUNNER)

    assert "run_rag_end_to_end_runtime_smoke.py" in script
    assert "run_rag_focused_tests.py" in script


def test_runner_emits_result_marker():
    script = read_text(RUNNER)

    assert "RAG_VERIFY_RESULT=" in script


def test_runner_default_work_dir_is_safe_smoke_path():
    script = read_text(RUNNER)

    assert "rag_e2e_runtime_smoke_verify" in script


def test_runner_states_verification_only_boundary():
    script = read_text(RUNNER)

    assert "Verification only" in script
    assert "does NOT" in script
    assert "human review gates" in script
    assert "docs/rag_agent_operator_runbook.md" in script


def test_doc_describes_runner_usage_and_boundary():
    doc = read_text(DOC)

    assert "scripts/run_rag_verify.ps1" in doc
    assert "-SmokeOnly" in doc
    assert "run_rag_end_to_end_runtime_smoke" in doc
    assert "run_rag_focused_tests.py" in doc
    assert ".venv" in doc
    assert "RAG_VERIFY_RESULT=" in doc
    assert "verification only" in doc.lower()
    assert "docs/rag_agent_operator_runbook.md" in doc
