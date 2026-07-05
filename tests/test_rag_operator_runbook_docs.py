from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNBOOK = "docs/rag_agent_operator_runbook.md"


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_runbook_file_exists():
    assert (ROOT / RUNBOOK).exists()


def test_runbook_documents_full_pipeline_run_order():
    docs = read_text(RUNBOOK)

    for marker in (
        "Step 060",
        "Step 061",
        "Step 062",
        "Step 063",
        "Step 064",
        "Step 065",
        "Step 066",
        "Step 067",
        "Step 068",
    ):
        assert marker in docs


def test_runbook_lists_required_commands():
    docs = read_text(RUNBOOK)

    for command in (
        "scripts\\run_rag_research_learning_loop.py",
        "scripts\\update_rag_research_memory_store.py",
        "scripts\\prepare_rag_memory_promotion_review.py",
        "scripts\\update_rag_memory_promotion_status.py",
        "scripts\\preview_rag_approved_memory_export.py",
        "scripts\\draft_rag_approved_memory_rule_candidates.py",
        "scripts\\validate_rag_rule_candidate_drafts.py",
        "scripts\\update_rag_rule_candidate_registry.py",
        "scripts\\preview_rag_trading_rule_export.py",
        "scripts\\run_rag_end_to_end_runtime_smoke.py",
        "scripts\\run_rag_focused_tests.py",
    ):
        assert command in docs


def test_runbook_uses_venv_python_invocation():
    docs = read_text(RUNBOOK)

    assert ".\\.venv\\Scripts\\python.exe" in docs


def test_runbook_documents_artifact_locations():
    docs = read_text(RUNBOOK)

    assert "agent_reports/rag_research_memory_store.jsonl" in docs
    assert "agent_reports/rag_rule_candidate_registry.jsonl" in docs


def test_runbook_documents_human_review_gates():
    docs = read_text(RUNBOOK)

    assert "human review gate" in docs
    assert "--status approved" in docs
    assert "approved_for_registry" in docs
    assert "draft_needs_human_review" in docs
    assert "registered_needs_final_review" in docs
    assert "preview_needs_human_review" in docs


def test_runbook_has_error_handling_and_verification_sections():
    docs = read_text(RUNBOOK)

    assert "## Error Handling" in docs
    assert "## Verification" in docs
    assert "failed_step" in docs


def test_runbook_states_boundaries():
    docs = read_text(RUNBOOK)

    assert "## Scope and Boundaries" in docs
    assert "not a real export" in docs.lower()
    assert "Trading Bot" in docs
    assert "data/" in docs
    assert "archive.db" in docs


def test_runbook_documents_safe_publishing_flow():
    docs = read_text(RUNBOOK)

    assert "review request" in docs
    assert "reviewer PASS" in docs
    assert "git add ." in docs
    assert "main`/`master" in docs
