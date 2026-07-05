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


def test_autonomous_loop_prints_operator_summary_contract():
    script = read_loop_script()

    assert "function Write-OperatorSummary" in script
    assert "RAG Autonomous Operator Summary" in script
    assert "total cycles: $TotalCycles" in script
    assert "completed cycles: $CompletedCycles" in script
    assert "successful cycles: $SuccessfulCycles" in script
    assert "stopped reason: $StoppedReason" in script
    assert "generated task list:" in script
    assert "completed task list:" in script
    assert "commit attempted count: $CommitAttemptedCount" in script
    assert "commit succeeded count: $CommitSucceededCount" in script
    assert "push attempted count: $PushAttemptedCount" in script
    assert "push succeeded count: $PushSucceededCount" in script
    assert "latest commit hash: $(Get-LatestCommitHash)" in script
    assert "final git status -sb:" in script
    assert "remaining pending summary:" in script
    assert "failed task summary:" in script
    assert "Write-OperatorSummary -TotalCycles $Cycles" in script


def test_autonomous_loop_collects_pipeline_summary_counts_and_task_lists():
    script = read_loop_script()

    assert 'Get-SummaryValue -PipelineOutput $pipelineOutput -Label "planner created task path"' in script
    assert 'Get-SummaryValue -PipelineOutput $pipelineOutput -Label "completed task path"' in script
    assert 'Get-SummaryValue -PipelineOutput $pipelineOutput -Label "commit attempted"' in script
    assert 'Get-SummaryValue -PipelineOutput $pipelineOutput -Label "commit succeeded"' in script
    assert 'Get-SummaryValue -PipelineOutput $pipelineOutput -Label "push attempted"' in script
    assert 'Get-SummaryValue -PipelineOutput $pipelineOutput -Label "push succeeded"' in script
    assert "$generatedTasks.Add($createdTaskPath)" in script
    assert "$completedTasks.Add($completedTaskPath)" in script
    assert "$commitAttemptedCount += 1" in script
    assert "$pushSucceededCount += 1" in script


def test_autonomous_loop_treats_planner_no_candidate_as_normal_no_action_stop():
    script = read_loop_script()

    assert '$plannerResult = Get-SummaryValue -PipelineOutput $pipelineOutput -Label "planner result"' in script
    assert 'if ($pipelineResult -eq "NO_ACTIONABLE_TASKS" -and $plannerResult -eq "NO_CANDIDATE")' in script
    assert '$stoppedReason = "no actionable RAG tasks and planner has no candidate"' in script
    assert "RAG autonomous loop stopped after cycle $cycle because planner returned no candidate." in script
    assert "$finalExitCode = 1" not in script.split('if ($pipelineResult -eq "NO_ACTIONABLE_TASKS" -and $plannerResult -eq "NO_CANDIDATE")', 1)[1].split("if (-not (Test-ContinueResult", 1)[0]


def test_autonomous_loop_preserves_archive_owned_protection_by_delegating_to_pipeline():
    script = read_loop_script()
    pipeline = (ROOT / "scripts" / "run_rag_agent_pipeline.ps1").read_text(encoding="utf-8")

    assert "run_rag_agent_pipeline.ps1" in script
    assert "agent_tasks/pending/001-real-daily-archive-wiring.md" in pipeline
    assert "function Test-ForbiddenPublishPath" in pipeline
