param(
  [switch]$CommitOnPass,
  [switch]$PushOnPass,
  [string]$CommitMessage = "RAG pipeline pass-gated update"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OnceScript = Join-Path $ScriptDir "run_rag_agent_once.ps1"
$ReviewScript = Join-Path $ScriptDir "review_rag_agent_run.ps1"

if (-not (Test-Path $OnceScript)) {
  throw "Missing runner: $OnceScript"
}
if (-not (Test-Path $ReviewScript)) {
  throw "Missing reviewer: $ReviewScript"
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
    [hashtable]$PublishResult
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
$pipelineExit = 0

Write-Host "Step 1: run_rag_agent_once.ps1 -NoPush"
& $OnceScript -NoPush
$runExit = $LASTEXITCODE
if ($runExit -ne 0) {
  Write-Host "RAG implementation step failed with exit code $runExit."
  $pipelineResult = "FAIL"
  $pipelineExit = $runExit
  Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -PublishResult $publishResult
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
  Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -PublishResult $publishResult
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

Write-PipelineSummary -PipelineResult $pipelineResult -ReviewResult $reviewResult -ReviewReport $reviewReport -PublishResult $publishResult
exit $pipelineExit
