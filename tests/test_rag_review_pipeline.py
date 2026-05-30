from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_review_pipeline_files_exist():
    assert (ROOT / "agent_prompts" / "rag_reviewer.md").exists()
    assert (ROOT / "scripts" / "review_rag_agent_run.ps1").exists()
    assert (ROOT / "scripts" / "run_rag_agent_pipeline.ps1").exists()


def test_review_script_is_read_only_and_runs_required_checks():
    script = read_text("scripts/review_rag_agent_run.ps1")

    forbidden_invocations = (
        "git add",
        "git commit",
        "git push",
        "& git add",
        "& git commit",
        "& git push",
    )
    for invocation in forbidden_invocations:
        assert invocation not in script

    assert '"git" @("status", "-sb")' in script
    assert '"git" @("diff", "--name-only")' in script
    assert '"git" @("diff", "--stat")' in script
    assert '"git" @("diff", "--check")' in script
    assert '"python" @("scripts\\run_rag_focused_tests.py")' in script
    assert '"python" @("scripts\\agent_next_task.py", "--list")' in script
    assert "PASS" in script
    assert "FAIL" in script
    assert "NEEDS_HUMAN_REVIEW" in script
    assert "agent_tasks/pending/001-real-daily-archive-wiring.md" in script


def test_pipeline_runs_no_push_then_review_without_automatic_publish():
    script = read_text("scripts/run_rag_agent_pipeline.ps1")

    assert "& $OnceScript -NoPush" in script
    assert "& $ReviewScript" in script
    assert "Waiting for user approval before any commit or push." in script
    assert "git add" not in script
    assert "git commit" not in script
    assert "git push" not in script


def test_reviewer_prompt_documents_review_decision_contract():
    prompt = read_text("agent_prompts/rag_reviewer.md")

    assert "Do not modify code" in prompt
    assert "Do not stage changes" in prompt
    assert "Do not create commits" in prompt
    assert "Do not push to any remote" in prompt
    assert "python scripts\\run_rag_focused_tests.py" in prompt
    assert "agent_tasks/pending/001-real-daily-archive-wiring.md" in prompt
    assert "PASS" in prompt
    assert "FAIL" in prompt
    assert "NEEDS_HUMAN_REVIEW" in prompt
