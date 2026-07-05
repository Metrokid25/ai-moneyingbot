[CmdletBinding()]
param(
  [switch]$Help,
  [switch]$CommitOnPass,
  [switch]$PushOnPass,
  [string]$CommitMessage = "",
  [string]$ManualTaskRef = "",
  [string]$ManualTaskTitle = "",
  [string]$ManualReviewOutDir = "agent_reports"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Help) {
  Write-Host @"
run_rag_agent_pipeline.ps1

Purpose:
  Run the guarded RAG task pipeline: implementation, focused verification,
  read-only review, and optional PASS-gated publishing.

Usage:
  .\scripts\run_rag_agent_pipeline.ps1
  .\scripts\run_rag_agent_pipeline.ps1 -ManualTaskRef "059-rag-manual-review-gate-pipeline-integration" -ManualTaskTitle "Manual review gate pipeline integration"
  .\scripts\run_rag_agent_pipeline.ps1 -CommitOnPass -PushOnPass -CommitMessage "Complete RAG task"

Manual task options:
  -ManualTaskRef <string>       Manual RAG task id, filename, or short reference.
  -ManualTaskTitle <string>     Optional human-readable title. Defaults to ManualTaskRef.
  -ManualReviewOutDir <string>  Directory for generated manual review prompt. Default: agent_reports.

Publish options:
  -CommitOnPass  Commit only after REVIEW_RESULT=PASS and the publish safety gate passes.
  -PushOnPass    Push only after a successful pass-gated commit. It has no effect without -CommitOnPass.

Safety:
  Push is forbidden before REVIEW_RESULT=PASS.
  Archive-owned 001-real-daily-archive-wiring.md tasks are BLOCKED FOR RAG IMPLEMENTATION.
  -Help prints this text only and does not run task selection, planner, implementation,
  review, manual review prompt generation, commit, or push.
"@
  exit 0
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot
$OnceScript = Join-Path $ScriptDir "run_rag_agent_once.ps1"
$ReviewScript = Join-Path $ScriptDir "review_rag_agent_run.ps1"
$PlannerScript = Join-Path $ScriptDir "plan_next_rag_task.py"
$TaskScript = Join-Path $ScriptDir "agent_next_task.py"
$ManualReviewScript = Join-Path $ScriptDir "prepare_manual_task_review.py"

if (-not (Test-Path $OnceScript)) {
  throw "Missing runner: $OnceScript"
}
if (-not (Test-Path $ReviewScript)) {
  throw "Missing reviewer: $ReviewScript"
}
if (-not (Test-Path $PlannerScript)) {
  throw "Missing planner: $PlannerScript"
}
if (-not (Test-Path $TaskScript)) {
  throw "Missing task helper: $TaskScript"
}
if (-not (Test-Path $ManualReviewScript)) {
  throw "Missing manual review helper: $ManualReviewScript"
}

function Get-ReviewMetadata {
  param([object[]]$ReviewOutput)

  $metadata = @{
    Result = "UNKNOWN"
    Report = ""
  }

  foreach ($item in $ReviewOutput) {
    $lines = ([string]$item) -split "\r?\n"
    foreach ($line in $lines) {
      $text = $line.Trim()
      if ($text -match "^REVIEW_RESULT=(PASS|FAIL|NEEDS_HUMAN_REVIEW|NO_ACTIONABLE_TASKS)$") {
        $metadata.Result = $Matches[1]
      } elseif ($text -match "^REVIEW_REPORT=(.+)$") {
        $metadata.Report = $Matches[1].Trim()
      }
    }
  }

  return $metadata
}

function Get-ChangedPaths {
  $paths = New-Object System.Collections.Generic.List[string]
  $statusLines = & git status --porcelain --untracked-files=all
  foreach ($line in $statusLines) {
    if ([string]::IsNullOrWhiteSpace($line) -or $line.Length -lt 4) {
      continue
    }
    $path = $line.Substring(3).Trim()
    if ($path.Contains(" -> ")) {
      $parts = $path -split " -> "
      foreach ($part in $parts) {
        $clean = $part.Trim().Trim('"').Replace("\", "/")
        if (-not [string]::IsNullOrWhiteSpace($clean)) {
          $paths.Add($clean)
        }
      }
    } else {
      $clean = $path.Trim('"').Replace("\", "/")
      if (-not [string]::IsNullOrWhiteSpace($clean)) {
        $paths.Add($clean)
      }
    }
  }
  return @($paths | Select-Object -Unique)
}

function Test-ForbiddenPublishPath {
  param([string]$Path)

  $p = $Path.Replace("\", "/")
  $forbiddenExact = @(
    ".env",
    "archive.db",
    "scripts/_step3_verify_v2.py",
    "scripts/daily_archive.py",
    "scripts/index_tail.py",
    "scripts/batch_recollect.py",
    "src/browser.py",
    "src/parser.py",
    "src/collector.py",
    "src/indexer.py",
    "agent_tasks/pending/001-real-daily-archive-wiring.md"
  )

  if ($forbiddenExact -contains $p) { return $true }
  if ($p.StartsWith("data/")) { return $true }
  return $false
}

function Get-RagTaskNameFromPath {
  param([string]$Path)

  $p = $Path.Replace("\", "/")
  $fileName = Split-Path -Leaf $p
  if ($fileName -eq "001-real-daily-archive-wiring.md") {
    return ""
  }
  if ($fileName -notmatch "^\d+-rag-.+\.md$") {
    return ""
  }
  return [System.IO.Path]::GetFileNameWithoutExtension($fileName)
}

function Resolve-PassGatedCommitMessage {
  param(
    [string]$ExplicitMessage,
    [hashtable]$PlannerResult,
    [string[]]$ChangedPaths
  )

  if (-not [string]::IsNullOrWhiteSpace($ExplicitMessage)) {
    return $ExplicitMessage
  }

  if ($PlannerResult.Result -eq "CREATED_TASK") {
    $plannedTask = Get-RagTaskNameFromPath -Path $PlannerResult.CreatedTaskPath
    if (-not [string]::IsNullOrWhiteSpace($plannedTask)) {
      return "Plan next RAG task: $plannedTask"
    }
  }

  foreach ($path in $ChangedPaths) {
    $p = $path.Replace("\", "/")
    if ($p.StartsWith("agent_tasks/done/")) {
      $completedTask = Get-RagTaskNameFromPath -Path $p
      if (-not [string]::IsNullOrWhiteSpace($completedTask)) {
        return "Complete RAG task: $completedTask"
      }
    }
  }

  return "RAG pipeline pass-gated update"
}

function Invoke-GitPublishCommand {
  param(
    [string]$FailureContext,
    [string[]]$Arguments
  )

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = & git @Arguments *>&1
    $exitCode = $LASTEXITCODE
  } catch {
    $output = @($_.Exception.Message)
    $exitCode = 1
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }

  $output | ForEach-Object { Write-Host $_ }
  if ($exitCode -ne 0) {
    Write-Host "Publish gate failed: $FailureContext failed with exit code $exitCode."
  }

  return $exitCode
}

function New-PublishResult {
  return @{
    ExitCode = 0
    CommitAttempted = $false
    CommitSucceeded = $false
    PushAttempted = $false
    PushSucceeded = $false
  }
}

function New-PlannerResult {
  return @{
    ExitCode = 0
    Result = "NOT_RUN"
    CreatedTaskPath = ""
    ExhaustionReportPath = ""
  }
}

function Test-NoActionableRagTask {
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = & python $TaskScript --status *>&1
    $exitCode = $LASTEXITCODE
  } catch {
    $output = @($_.Exception.Message)
    $exitCode = 1
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }

  if ($exitCode -ne 0) {
    Write-Host "Unable to determine pending RAG task status."
    $output | ForEach-Object { Write-Host $_ }
    return $false
  }

  $lines = @($output | ForEach-Object { ([string]$_).Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
  $hasNoActionResult = $lines.Count -gt 0 -and $lines[0] -eq "NO_ACTIONABLE_TASKS"
  $skipsArchiveOwnedTask = $lines -contains "skipped=agent_tasks\pending\001-real-daily-archive-wiring.md"
  return ($hasNoActionResult -and $skipsArchiveOwnedTask)
}

function Invoke-RagPlanner {
  $result = New-PlannerResult
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = & python $PlannerScript *>&1
    $exitCode = $LASTEXITCODE
  } catch {
    $output = @($_.Exception.Message)
    $exitCode = 1
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }

  $result.ExitCode = $exitCode
  $output | ForEach-Object { Write-Host $_ }
  foreach ($line in $output) {
    $text = ([string]$line).Trim()
    if ($text -match "^PLANNER_CREATED_TASK=(.+)$") {
      $result.Result = "CREATED_TASK"
      $result.CreatedTaskPath = $Matches[1].Trim()
    } elseif ($text -match "^PLANNER_SKIPPED_ACTIONABLE_TASK=(.+)$") {
      $result.Result = "SKIPPED_ACTIONABLE_TASK"
      $result.CreatedTaskPath = $Matches[1].Trim()
    } elseif ($text -eq "PLANNER_NO_CANDIDATE") {
      $result.Result = "NO_CANDIDATE"
    } elseif ($text -match "^PLANNER_EXHAUSTION_REPORT=(.+)$") {
      $result.ExhaustionReportPath = $Matches[1].Trim()
    }
  }

  if ($exitCode -ne 0) {
    $result.Result = "FAILED"
  }
  return $result
}

function New-ManualReviewResult {
  return @{
    Enabled = $false
    ExitCode = 0
    ReportPath = ""
    Blocked = $false
  }
}

function Invoke-ManualReviewGate {
  param(
    [string]$TaskRef,
    [string]$TaskTitle,
    [string]$OutDir
  )

  $result = New-ManualReviewResult
  if ([string]::IsNullOrWhiteSpace($TaskRef)) {
    return $result
  }

  $result.Enabled = $true
  $resolvedTitle = if ([string]::IsNullOrWhiteSpace($TaskTitle)) { $TaskRef } else { $TaskTitle }
  $manualArgs = @(
    "scripts\prepare_manual_task_review.py",
    $TaskRef,
    "--task-title",
    $resolvedTitle,
    "--out-dir",
    $OutDir
  )

  Write-Host "Step 2: prepare_manual_task_review.py"
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = & python @manualArgs *>&1
    $exitCode = $LASTEXITCODE
  } catch {
    $output = @($_.Exception.Message)
    $exitCode = 1
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }

  $result.ExitCode = $exitCode
  $output | ForEach-Object { Write-Host $_ }
  foreach ($line in $output) {
    $text = ([string]$line).Trim()
    if ($text -match "^Wrote manual RAG task review prompt:\s*(.+)$") {
      $result.ReportPath = $Matches[1].Trim()
    }
  }

  if ($exitCode -ne 0) {
    $result.Blocked = $true
    return $result
  }

  if (-not [string]::IsNullOrWhiteSpace($result.ReportPath) -and (Test-Path $result.ReportPath)) {
    $content = Get-Content -Path $result.ReportPath -Raw -Encoding UTF8
    if ($content -match "BLOCKED FOR RAG IMPLEMENTATION") {
      $result.Blocked = $true
    }
  }

  return $result
}

function Test-ManualReviewGateBlocked {
  param(
    [string]$TaskRef,
    [string]$TaskTitle
  )

  if ([string]::IsNullOrWhiteSpace($TaskRef)) {
    return $false
  }

  $resolvedTitle = if ([string]::IsNullOrWhiteSpace($TaskTitle)) { $TaskRef } else { $TaskTitle }
  $manualArgs = @(
    "scripts\prepare_manual_task_review.py",
    $TaskRef,
    "--task-title",
    $resolvedTitle
  )

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = & python @manualArgs *>&1
    $exitCode = $LASTEXITCODE
  } catch {
    $output = @($_.Exception.Message)
    $exitCode = 1
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }

  if ($exitCode -ne 0) {
    return $true
  }

  return (($output | Out-String) -match "BLOCKED FOR RAG IMPLEMENTATION")
}

function Invoke-PassGatedPublish {
  param(
    [string]$Message,
    [hashtable]$PlannerResult,
    [switch]$Commit,
    [switch]$Push
  )

  $result = New-PublishResult

  if (-not $Commit) {
    if ($Push) {
      Write-Host "PushOnPass requested without CommitOnPass. No push will run without a successful pass-gated commit."
    }
    Write-Host "Pipeline passed review. Waiting for user approval before any commit or push."
    return $result
  }

  $changedPaths = @(Get-ChangedPaths)
  if ($changedPaths.Count -eq 0) {
    Write-Host "Publish gate failed: no changed files to commit."
    $result.ExitCode = 1
    return $result
  }

  $forbiddenPaths = @($changedPaths | Where-Object { Test-ForbiddenPublishPath $_ })
  if ($forbiddenPaths.Count -gt 0) {
    Write-Host "Publish gate failed: forbidden files changed."
    foreach ($path in $forbiddenPaths) {
      Write-Host "Forbidden changed file: $path"
    }
    $result.ExitCode = 1
    return $result
  }

  $resolvedMessage = Resolve-PassGatedCommitMessage -ExplicitMessage $Message -PlannerResult $PlannerResult -ChangedPaths $changedPaths
  Write-Host "Pass-gated commit message: $resolvedMessage"

  Write-Host "Publish gate passed. Staging git status changed files only."
  foreach ($path in $changedPaths) {
    $addExit = Invoke-GitPublishCommand -FailureContext "git add for $path" -Arguments @("add", "--", $path)
    if ($addExit -ne 0) {
      $result.ExitCode = $addExit
      return $result
    }
  }

  $result.CommitAttempted = $true
  $commitExit = Invoke-GitPublishCommand -FailureContext "git commit" -Arguments @("commit", "-m", $resolvedMessage)
  if ($commitExit -ne 0) {
    $result.ExitCode = $commitExit
    return $result
  }
  $result.CommitSucceeded = $true

  if (-not $Push) {
    Write-Host "Pass-gated commit completed. PushOnPass not requested; push skipped."
    return $result
  }

  $result.PushAttempted = $true
  $pushExit = Invoke-GitPublishCommand -FailureContext "git push" -Arguments @("push")
  if ($pushExit -ne 0) {
    $result.ExitCode = $pushExit
    return $result
  }
  $result.PushSucceeded = $true

  Write-Host "Pass-gated push completed."
  return $result
}

function Get-LatestCommitHash {
  $hash = & git rev-parse --short HEAD 2>$null
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($hash)) {
    return "(unavailable)"
  }
  return ([string]$hash).Trim()
}

function Get-GitStatusSummary {
  $status = & git status -sb 2>&1
  if ($LASTEXITCODE -ne 0) {
    return @("git status -sb failed")
  }
  return @($status)
}

function Get-RemainingPendingTaskSummary {
  $taskOutput = & python scripts\agent_next_task.py --list 2>&1
  if ($LASTEXITCODE -ne 0) {
    return @("agent_next_task.py --list failed")
  }
  return @($taskOutput)
}

function Get-PendingRagTaskAudit {
  $taskOutput = & python scripts\agent_next_task.py --status 2>&1
  if ($LASTEXITCODE -ne 0) {
    return @("agent_next_task.py --status failed")
  }
  return @($taskOutput)
}

function Format-BooleanResult {
  param([bool]$Value)
  if ($Value) { return "yes" }
  return "no"
}

function Write-PipelineSummary {
  param(
    [string]$PipelineResult,
    [string]$ReviewResult,
    [string]$ReviewReport,
    [hashtable]$ManualReviewResult,
    [hashtable]$PublishResult,
    [hashtable]$PlannerResult
  )

  Write-Host ""
  Write-Host "RAG Pipeline Summary"
  Write-Host "pipeline result: $PipelineResult"
  Write-Host "review result: $ReviewResult"
  if ([string]::IsNullOrWhiteSpace($ReviewReport)) {
    Write-Host "review report path: (none)"
  } else {
    Write-Host "review report path: $ReviewReport"
  }
  Write-Host "manual review gate enabled: $(Format-BooleanResult $ManualReviewResult.Enabled)"
  if ([string]::IsNullOrWhiteSpace($ManualReviewResult.ReportPath)) {
    Write-Host "manual review prompt path: (none)"
  } else {
    Write-Host "manual review prompt path: $($ManualReviewResult.ReportPath)"
  }
  Write-Host "manual review gate blocked: $(Format-BooleanResult $ManualReviewResult.Blocked)"
  Write-Host "commit attempted: $(Format-BooleanResult $PublishResult.CommitAttempted)"
  Write-Host "commit succeeded: $(Format-BooleanResult $PublishResult.CommitSucceeded)"
  Write-Host "push attempted: $(Format-BooleanResult $PublishResult.PushAttempted)"
  Write-Host "push succeeded: $(Format-BooleanResult $PublishResult.PushSucceeded)"
  Write-Host "planner result: $($PlannerResult.Result)"
  if ([string]::IsNullOrWhiteSpace($PlannerResult.CreatedTaskPath)) {
    Write-Host "planner created task path: (none)"
  } else {
    Write-Host "planner created task path: $($PlannerResult.CreatedTaskPath)"
  }
  if ([string]::IsNullOrWhiteSpace($PlannerResult.ExhaustionReportPath)) {
    Write-Host "planner exhaustion report path: (none)"
  } else {
    Write-Host "planner exhaustion report path: $($PlannerResult.ExhaustionReportPath)"
  }
  Write-Host "latest commit hash: $(Get-LatestCommitHash)"
  Write-Host "git status -sb:"
  foreach ($line in @(Get-GitStatusSummary)) {
    Write-Host "  $line"
  }
  Write-Host "remaining pending task summary:"
  foreach ($line in @(Get-RemainingPendingTaskSummary)) {
    Write-Host "  $line"
  }
  Write-Host "pending RAG task audit:"
  foreach ($line in @(Get-PendingRagTaskAudit)) {
    Write-Host "  $line"
  }
}

Write-Host "Starting RAG agent pipeline."
$pipelineResult = "UNKNOWN"
$reviewResult = "UNKNOWN"
$reviewReport = ""
$manualReviewResult = New-ManualReviewResult
$publishResult = New-PublishResult
$plannerResult = New-PlannerResult
$pipelineExit = 0

if (Test-ManualReviewGateBlocked -TaskRef $ManualTaskRef -TaskTitle $ManualTaskTitle) {
  Write-Host "Pipeline stopped before implementation: manual task review gate returned BLOCKED FOR RAG IMPLEMENTATION."
  $pipelineResult = "FAIL"
  $pipelineExit = 1
  $manualReviewResult.Enabled = $true
  $manualReviewResult.Blocked = $true
  Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -ManualReviewResult $manualReviewResult -PublishResult $publishResult -PlannerResult $plannerResult
  exit $pipelineExit
}

if (Test-NoActionableRagTask) {
  Write-Host "No actionable RAG task found. Running one-shot RAG planner."
  $reviewResult = "NO_ACTIONABLE_TASKS"
  $plannerResult = Invoke-RagPlanner
  if ($plannerResult.ExitCode -ne 0) {
    $pipelineResult = "FAIL"
    $pipelineExit = $plannerResult.ExitCode
  } elseif ($plannerResult.Result -eq "CREATED_TASK") {
    Write-Host "Planner created a task for a later pipeline run: $($plannerResult.CreatedTaskPath)"
    $pipelineResult = "PLANNER_CREATED_TASK"
    $publishResult = Invoke-PassGatedPublish -Message $CommitMessage -PlannerResult $plannerResult -Commit:$CommitOnPass -Push:$PushOnPass
    $pipelineExit = $publishResult.ExitCode
    if ($pipelineExit -ne 0) {
      $pipelineResult = "FAIL"
    }
  } else {
    Write-Host "Planner did not create a task. No commit or push will run."
    $pipelineResult = "NO_ACTIONABLE_TASKS"
  }
  Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -ManualReviewResult $manualReviewResult -PublishResult $publishResult -PlannerResult $plannerResult
  exit $pipelineExit
}

Write-Host "Step 1: run_rag_agent_once.ps1 -NoPush"
& $OnceScript -NoPush
$runExit = $LASTEXITCODE
if ($runExit -ne 0) {
  Write-Host "RAG implementation step failed with exit code $runExit."
  $pipelineResult = "FAIL"
  $pipelineExit = $runExit
  Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -ManualReviewResult $manualReviewResult -PublishResult $publishResult -PlannerResult $plannerResult
  exit $pipelineExit
}

$manualReviewResult = Invoke-ManualReviewGate -TaskRef $ManualTaskRef -TaskTitle $ManualTaskTitle -OutDir $ManualReviewOutDir
if ($manualReviewResult.ExitCode -ne 0 -or $manualReviewResult.Blocked) {
  Write-Host "Pipeline stopped after manual review gate failure. Commit and push are forbidden."
  $pipelineResult = "FAIL"
  $pipelineExit = 1
  Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -ManualReviewResult $manualReviewResult -PublishResult $publishResult -PlannerResult $plannerResult
  exit $pipelineExit
}

Write-Host "Step 3: review_rag_agent_run.ps1"
$reviewOutput = & $ReviewScript *>&1
$reviewExit = $LASTEXITCODE
$reviewOutput | ForEach-Object { Write-Host $_ }

$reviewMetadata = Get-ReviewMetadata -ReviewOutput $reviewOutput
$reviewResult = $reviewMetadata.Result
$reviewReport = $reviewMetadata.Report

Write-Host "Pipeline review result: $reviewResult"
if (-not [string]::IsNullOrWhiteSpace($reviewReport)) {
  Write-Host "Pipeline review report: $reviewReport"
}

if ($reviewExit -ne 0 -or $reviewResult -eq "FAIL") {
  Write-Host "Pipeline stopped after review failure. Inspect the review report before continuing."
  $pipelineResult = "FAIL"
  $pipelineExit = 1
  Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -ManualReviewResult $manualReviewResult -PublishResult $publishResult -PlannerResult $plannerResult
  exit $pipelineExit
}

if ($reviewResult -eq "PASS") {
  $publishResult = Invoke-PassGatedPublish -Message $CommitMessage -PlannerResult $plannerResult -Commit:$CommitOnPass -Push:$PushOnPass
  if ($publishResult.ExitCode -eq 0) {
    $pipelineResult = "PASS"
  } else {
    $pipelineResult = "FAIL"
  }
  $pipelineExit = $publishResult.ExitCode
} elseif ($reviewResult -eq "NO_ACTIONABLE_TASKS") {
  Write-Host "Pipeline found no actionable RAG task. No commit or push will run."
  $pipelineResult = "NO_ACTIONABLE_TASKS"
} else {
  Write-Host "Pipeline needs human review. Waiting for user approval before any commit or push."
  $pipelineResult = "NEEDS_HUMAN_REVIEW"
}

Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -ManualReviewResult $manualReviewResult -PublishResult $publishResult -PlannerResult $plannerResult
exit $pipelineExit
