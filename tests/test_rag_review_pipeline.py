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
    assert "NO_ACTIONABLE_TASKS" in script
    assert "agent_tasks/pending/001-real-daily-archive-wiring.md" in script


def test_pipeline_runs_no_push_then_review_with_publish_options_defaulting_off():
    script = read_text("scripts/run_rag_agent_pipeline.ps1")

    assert "[switch]$CommitOnPass" in script
    assert "[switch]$PushOnPass" in script
    assert '[string]$CommitMessage = "RAG pipeline pass-gated update"' in script
    assert "& $OnceScript -NoPush" in script
    assert "& $ReviewScript" in script
    assert "Waiting for user approval before any commit or push." in script
    assert 'if (-not $Commit)' in script
    assert "Pipeline passed review. Waiting for user approval before any commit or push." in script


def test_pipeline_commits_and_pushes_only_through_pass_gated_options():
    script = read_text("scripts/run_rag_agent_pipeline.ps1")

    assert "function Invoke-PassGatedPublish" in script
    assert 'if ($reviewResult -eq "PASS")' in script
    assert "Invoke-PassGatedPublish -Message $CommitMessage -Commit:$CommitOnPass -Push:$PushOnPass" in script
    assert 'Invoke-GitPublishCommand -FailureContext "git commit" -Arguments @("commit", "-m", $Message)' in script
    assert 'if (-not $Push)' in script
    assert 'Invoke-GitPublishCommand -FailureContext "git push" -Arguments @("push")' in script
    assert "PushOnPass not requested; push skipped." in script
    assert "Pipeline needs human review. Waiting for user approval before any commit or push." in script
    assert "Pipeline stopped after review failure. Inspect the review report before continuing." in script
    assert "Pipeline found no actionable RAG task. No commit or push will run." in script


def test_pipeline_stages_only_git_status_changed_paths_without_add_dot():
    script = read_text("scripts/run_rag_agent_pipeline.ps1")

    assert "function Get-ChangedPaths" in script
    assert "git status --porcelain --untracked-files=all" in script
    assert "foreach ($path in $changedPaths)" in script
    assert 'Invoke-GitPublishCommand -FailureContext "git add for $path" -Arguments @("add", "--", $path)' in script
    assert "git add ." not in script
    assert "& git add ." not in script


def test_pipeline_tolerates_git_warning_output_and_uses_exit_codes():
    script = read_text("scripts/run_rag_agent_pipeline.ps1")

    assert "function Invoke-GitPublishCommand" in script
    assert '$previousErrorActionPreference = $ErrorActionPreference' in script
    assert '$ErrorActionPreference = "Continue"' in script
    assert "$output = & git @Arguments *>&1" in script
    assert "$exitCode = $LASTEXITCODE" in script
    assert "$output | ForEach-Object { Write-Host $_ }" in script
    assert "if ($exitCode -ne 0)" in script
    assert "return $exitCode" in script


def test_pipeline_blocks_forbidden_and_archive_owned_paths_before_publish():
    script = read_text("scripts/run_rag_agent_pipeline.ps1")

    assert "function Test-ForbiddenPublishPath" in script
    assert '".env"' in script
    assert '"archive.db"' in script
    assert 'if ($p.StartsWith("data/")) { return $true }' in script
    assert '"scripts/_step3_verify_v2.py"' in script
    assert '"scripts/daily_archive.py"' in script
    assert '"scripts/index_tail.py"' in script
    assert '"scripts/batch_recollect.py"' in script
    assert '"src/browser.py"' in script
    assert '"src/parser.py"' in script
    assert '"src/collector.py"' in script
    assert '"src/indexer.py"' in script
    assert '"agent_tasks/pending/001-real-daily-archive-wiring.md"' in script
    assert "Publish gate failed: forbidden files changed." in script


def test_pipeline_parses_review_result_and_report_lines():
    script = read_text("scripts/run_rag_agent_pipeline.ps1")

    assert "function Get-ReviewMetadata" in script
    assert "& $ReviewScript *>&1" in script
    assert 'REVIEW_RESULT=(PASS|FAIL|NEEDS_HUMAN_REVIEW|NO_ACTIONABLE_TASKS)' in script
    assert 'REVIEW_REPORT=(.+)' in script
    assert "$reviewMetadata = Get-ReviewMetadata -ReviewOutput $reviewOutput" in script
    assert "Pipeline review result: $reviewResult" in script
    assert "Pipeline review report: $reviewReport" in script


def test_pipeline_prints_final_human_readable_summary_contract():
    script = read_text("scripts/run_rag_agent_pipeline.ps1")

    assert "function Write-PipelineSummary" in script
    assert "RAG Pipeline Summary" in script
    assert "pipeline result: $PipelineResult" in script
    assert "review result: $ReviewResult" in script
    assert "review report path: $ReviewReport" in script
    assert "commit attempted: $(Format-BooleanResult $PublishResult.CommitAttempted)" in script
    assert "commit succeeded: $(Format-BooleanResult $PublishResult.CommitSucceeded)" in script
    assert "push attempted: $(Format-BooleanResult $PublishResult.PushAttempted)" in script
    assert "push succeeded: $(Format-BooleanResult $PublishResult.PushSucceeded)" in script
    assert "latest commit hash: $(Get-LatestCommitHash)" in script
    assert "git status -sb:" in script
    assert "remaining pending task summary:" in script
    assert "git rev-parse --short HEAD" in script
    assert "git status -sb" in script
    assert "python scripts\\agent_next_task.py --list" in script


def test_pipeline_summary_is_written_for_all_review_outcomes_and_run_failure():
    script = read_text("scripts/run_rag_agent_pipeline.ps1")

    assert 'if ($reviewResult -eq "PASS")' in script
    assert '$pipelineResult = "PASS"' in script
    assert '$pipelineResult = "NO_ACTIONABLE_TASKS"' in script
    assert '$pipelineResult = "NEEDS_HUMAN_REVIEW"' in script
    assert '$pipelineResult = "FAIL"' in script
    assert "Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -PublishResult $publishResult" in script


def test_once_runner_runs_planner_when_no_actionable_rag_task_exists():
    script = read_text("scripts/run_rag_agent_once.ps1")

    assert "python scripts/agent_next_task.py --status" in script
    assert "NO_ACTIONABLE_TASKS: no actionable RAG pending task. Codex exec, commit, and push skipped." in script
    assert '"python" @("scripts\\plan_next_rag_task.py")' in script
    assert "RUN_RESULT=PLANNER_RUN" in script


def test_review_script_keeps_no_actionable_tasks_distinct_from_human_review():
    script = read_text("scripts/review_rag_agent_run.ps1")

    assert '"python" @("scripts\\agent_next_task.py", "--status")' in script
    assert '$decision = "NO_ACTIONABLE_TASKS"' in script
    assert '$decision -ne "NO_ACTIONABLE_TASKS"' in script


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
