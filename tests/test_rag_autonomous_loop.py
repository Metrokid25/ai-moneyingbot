from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def read_loop_script() -> str:
    return (ROOT / "scripts" / "run_rag_autonomous_loop.ps1").read_text(encoding="utf-8")


def test_autonomous_loop_script_exists_and_uses_bounded_cycles():
    script = read_loop_script()

    assert "[int]$Cycles = 1" in script
    assert 'throw "Cycles must be at least 1."' in script
    assert "for ($cycle = 1; $cycle -le $Cycles; $cycle += 1)" in script
    assert '$PipelineScript = Join-Path $ScriptDir "run_rag_agent_pipeline.ps1"' in script
    assert "& $PipelineScript @pipelineArgs *>&1" in script


def test_autonomous_loop_forwards_publish_options_only_when_requested():
    script = read_loop_script()

    assert "[switch]$CommitOnPass" in script
    assert "[switch]$PushOnPass" in script
    assert "$pipelineArgs = @{}" in script
    assert 'if ($CommitOnPass) { $pipelineArgs.CommitOnPass = $true }' in script
    assert 'if ($PushOnPass) { $pipelineArgs.PushOnPass = $true }' in script
    assert '[string]$CommitMessage = ""' in script
    assert '$PSBoundParameters.ContainsKey("CommitMessage")' in script
    assert '$pipelineArgs.CommitMessage = $CommitMessage' in script
    assert "& $PipelineScript @pipelineArgs *>&1" in script
    assert "git add ." not in script
    assert "git commit" not in script
    assert "git push" not in script


def test_autonomous_loop_default_does_not_forward_publish_options():
    script = read_loop_script()

    assert "$pipelineArgs = @{}" in script
    assert "CommitOnPass = $false" not in script
    assert "PushOnPass = $false" not in script
    assert 'if ($CommitOnPass)' in script
    assert 'if ($PushOnPass)' in script


def test_autonomous_loop_continues_only_on_allowed_success_states():
    script = read_loop_script()

    assert "function Get-PipelineResult" in script
    assert "pipeline result: (PASS|FAIL|PLANNER_CREATED_TASK|NO_ACTIONABLE_TASKS|NEEDS_HUMAN_REVIEW)" in script
    assert '@("PASS", "PLANNER_CREATED_TASK", "NO_ACTIONABLE_TASKS") -contains $PipelineResult' in script
    assert '@("FAIL", "NEEDS_HUMAN_REVIEW") -contains $PipelineResult' in script
    assert "RAG autonomous cycle $cycle result: $pipelineResult (exit code $pipelineExitCode)" in script
    assert "RAG autonomous loop stopped after cycle $cycle on terminal state $pipelineResult." in script


def test_autonomous_loop_preserves_archive_owned_protection_by_delegating_to_pipeline():
    script = read_loop_script()
    pipeline = (ROOT / "scripts" / "run_rag_agent_pipeline.ps1").read_text(encoding="utf-8")

    assert "run_rag_agent_pipeline.ps1" in script
    assert "agent_tasks/pending/001-real-daily-archive-wiring.md" in pipeline
    assert "function Test-ForbiddenPublishPath" in pipeline
