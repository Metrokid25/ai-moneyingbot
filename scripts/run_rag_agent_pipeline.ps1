param(
  [switch]$CommitOnPass,
  [switch]$PushOnPass,
  [string]$CommitMessage = "RAG pipeline pass-gated update"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot
$OnceScript = Join-Path $ScriptDir "run_rag_agent_once.ps1"
$ReviewScript = Join-Path $ScriptDir "review_rag_agent_run.ps1"
$PlannerScript = Join-Path $ScriptDir "plan_next_rag_task.py"
$TaskScript = Join-Path $ScriptDir "agent_next_task.py"

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
    }
  }

  if ($exitCode -ne 0) {
    $result.Result = "FAILED"
  }
  return $result
}

function Invoke-PassGatedPublish {
  param(
    [string]$Message,
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

  Write-Host "Publish gate passed. Staging git status changed files only."
  foreach ($path in $changedPaths) {
    $addExit = Invoke-GitPublishCommand -FailureContext "git add for $path" -Arguments @("add", "--", $path)
    if ($addExit -ne 0) {
      $result.ExitCode = $addExit
      return $result
    }
  }

  $result.CommitAttempted = $true
  $commitExit = Invoke-GitPublishCommand -FailureContext "git commit" -Arguments @("commit", "-m", $Message)
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
  Write-Host "latest commit hash: $(Get-LatestCommitHash)"
  Write-Host "git status -sb:"
  foreach ($line in @(Get-GitStatusSummary)) {
    Write-Host "  $line"
  }
  Write-Host "remaining pending task summary:"
  foreach ($line in @(Get-RemainingPendingTaskSummary)) {
    Write-Host "  $line"
  }
}

Write-Host "Starting RAG agent pipeline."
$pipelineResult = "UNKNOWN"
$reviewResult = "UNKNOWN"
$reviewReport = ""
$publishResult = New-PublishResult
$plannerResult = New-PlannerResult
$pipelineExit = 0

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
    $publishResult = Invoke-PassGatedPublish -Message $CommitMessage -Commit:$CommitOnPass -Push:$PushOnPass
    $pipelineExit = $publishResult.ExitCode
    if ($pipelineExit -ne 0) {
      $pipelineResult = "FAIL"
    }
  } else {
    Write-Host "Planner did not create a task. No commit or push will run."
    $pipelineResult = "NO_ACTIONABLE_TASKS"
  }
  Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -PublishResult $publishResult -PlannerResult $plannerResult
  exit $pipelineExit
}

Write-Host "Step 1: run_rag_agent_once.ps1 -NoPush"
& $OnceScript -NoPush
$runExit = $LASTEXITCODE
if ($runExit -ne 0) {
  Write-Host "RAG implementation step failed with exit code $runExit."
  $pipelineResult = "FAIL"
  $pipelineExit = $runExit
  Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -PublishResult $publishResult -PlannerResult $plannerResult
  exit $pipelineExit
}

Write-Host "Step 2: review_rag_agent_run.ps1"
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
  Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -PublishResult $publishResult -PlannerResult $plannerResult
  exit $pipelineExit
}

if ($reviewResult -eq "PASS") {
  $publishResult = Invoke-PassGatedPublish -Message $CommitMessage -Commit:$CommitOnPass -Push:$PushOnPass
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

Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -PublishResult $publishResult -PlannerResult $plannerResult
exit $pipelineExit
