from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_autorunner_files_exist():
    assert (ROOT / "agent_prompts" / "rag_autorunner.md").exists()
    assert (ROOT / "scripts" / "run_rag_agent_once.ps1").exists()
    assert (ROOT / "scripts" / "run_rag_agent_loop.ps1").exists()
    assert (ROOT / "docs" / "rag_autorunner.md").exists()


def test_autorunner_prompt_forbids_unsafe_git_operations():
    prompt = read_text("agent_prompts/rag_autorunner.md")

    assert "Do not run `git add .`." in prompt
    assert "Never commit or push main/master automatically." in prompt


def test_docs_describe_reports_and_commit_flags():
    docs = read_text("docs/rag_autorunner.md")

    assert "agent_reports/" in docs
    assert "-NoCommit" in docs
    assert "-NoPush" in docs


def test_once_script_has_allowlist_validation_without_bulk_stage():
    script = read_text("scripts/run_rag_agent_once.ps1")

    assert "Test-AllowlistedPath" in script
    assert "allowlist" in script.lower()
    assert "git add ." not in script


def test_once_script_captures_codex_output_and_exit_code():
    script = read_text("scripts/run_rag_agent_once.ps1")

    assert "$PromptText | & codex exec --sandbox workspace-write -" in script
    assert "1> $stdoutPath" in script
    assert "2> $stderrPath" in script
    assert "codex_exit_code=$codexExit" in script


def test_once_script_blocks_commit_when_codex_fails():
    script = read_text("scripts/run_rag_agent_once.ps1")

    assert "$codexFailed = $true" in script
    assert "blocked: codex exec failed" in script
    assert "$canCommit = $false" in script
