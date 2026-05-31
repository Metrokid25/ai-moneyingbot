param(
  [int]$Cycles = 1,
  [switch]$CommitOnPass,
  [switch]$PushOnPass,
  [string]$CommitMessage = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot
$PipelineScript = Join-Path $ScriptDir "run_rag_agent_pipeline.ps1"

if (-not (Test-Path $PipelineScript)) {
  throw "Missing pipeline runner: $PipelineScript"
}

if ($Cycles -lt 1) {
  throw "Cycles must be at least 1."
}

function Get-PipelineResult {
  param([object[]]$PipelineOutput)

  $result = "UNKNOWN"
  foreach ($item in $PipelineOutput) {
    $lines = ([string]$item) -split "\r?\n"
    foreach ($line in $lines) {
      $text = $line.Trim()
      if ($text -match "^pipeline result: (PASS|FAIL|PLANNER_CREATED_TASK|NO_ACTIONABLE_TASKS|NEEDS_HUMAN_REVIEW)$") {
        $result = $Matches[1]
      }
    }
  }
  return $result
}

function Get-SummaryValue {
  param(
    [object[]]$PipelineOutput,
    [string]$Label
  )

  foreach ($item in $PipelineOutput) {
    $lines = ([string]$item) -split "\r?\n"
    foreach ($line in $lines) {
      $text = $line.Trim()
      if ($text.StartsWith("${Label}:")) {
        return $text.Substring($Label.Length + 1).Trim()
      }
    }
  }
  return ""
}

function Test-YesSummaryValue {
  param([string]$Value)
  return $Value -eq "yes"
}

function Get-LatestCommitHash {
  $hash = & git rev-parse --short HEAD 2>$null
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($hash)) {
    return "(unavailable)"
  }
  return ([string]$hash).Trim()
}

function Get-GitStatusLines {
  $status = & git status -sb 2>&1
  if ($LASTEXITCODE -ne 0) {
    return @("git status -sb failed")
  }
  return @($status)
}

function Get-TaskListLines {
  $taskOutput = & python scripts\agent_next_task.py --list 2>&1
  if ($LASTEXITCODE -ne 0) {
    return @("agent_next_task.py --list failed")
  }
  return @($taskOutput)
}

function Get-QueueSummaryLines {
  param([string]$QueueName)

  $lines = @(Get-TaskListLines)
  $summary = New-Object System.Collections.Generic.List[string]
  $inQueue = $false
  foreach ($line in $lines) {
    $text = ([string]$line).TrimEnd()
    if ($text -eq "${QueueName}:") {
      $inQueue = $true
      continue
    }
    if ($inQueue -and $text -match "^(pending|running|done|failed):$") {
      break
    }
    if ($inQueue) {
      $summary.Add($text)
    }
  }
  if ($summary.Count -eq 0) {
    $summary.Add("  - (none)")
  }
  return $summary.ToArray()
}

function Test-ContinueResult {
  param([string]$PipelineResult)

  return @("PASS", "PLANNER_CREATED_TASK", "NO_ACTIONABLE_TASKS") -contains $PipelineResult
}

function Test-StopResult {
  param([string]$PipelineResult)

  return @("FAIL", "NEEDS_HUMAN_REVIEW") -contains $PipelineResult
}

function Write-OperatorSummary {
  param(
    [int]$TotalCycles,
    [int]$CompletedCycles,
    [int]$SuccessfulCycles,
    [string]$StoppedReason,
    [string[]]$GeneratedTasks,
    [string[]]$CompletedTasks,
    [int]$CommitAttemptedCount,
    [int]$CommitSucceededCount,
    [int]$PushAttemptedCount,
    [int]$PushSucceededCount
  )

  Write-Host ""
  Write-Host "RAG Autonomous Operator Summary"
  Write-Host "total cycles: $TotalCycles"
  Write-Host "completed cycles: $CompletedCycles"
  Write-Host "successful cycles: $SuccessfulCycles"
  Write-Host "stopped reason: $StoppedReason"
  Write-Host "generated task list:"
  if ($GeneratedTasks.Count -eq 0) {
    Write-Host "  - (none)"
  } else {
    foreach ($task in $GeneratedTasks) { Write-Host "  - $task" }
  }
  Write-Host "completed task list:"
  if ($CompletedTasks.Count -eq 0) {
    Write-Host "  - (none)"
  } else {
    foreach ($task in $CompletedTasks) { Write-Host "  - $task" }
  }
  Write-Host "commit attempted count: $CommitAttemptedCount"
  Write-Host "commit succeeded count: $CommitSucceededCount"
  Write-Host "push attempted count: $PushAttemptedCount"
  Write-Host "push succeeded count: $PushSucceededCount"
  Write-Host "latest commit hash: $(Get-LatestCommitHash)"
  Write-Host "final git status -sb:"
  foreach ($line in @(Get-GitStatusLines)) { Write-Host "  $line" }
  Write-Host "remaining pending summary:"
  foreach ($line in @(Get-QueueSummaryLines -QueueName "pending")) { Write-Host "  $line" }
  Write-Host "failed task summary:"
  foreach ($line in @(Get-QueueSummaryLines -QueueName "failed")) { Write-Host "  $line" }
}

Write-Host "Starting RAG autonomous loop for $Cycles cycle(s)."
$finalExitCode = 0
$completedCycles = 0
$successfulCycles = 0
$stoppedReason = "completed requested cycles"
$generatedTasks = New-Object System.Collections.Generic.List[string]
$completedTasks = New-Object System.Collections.Generic.List[string]
$commitAttemptedCount = 0
$commitSucceededCount = 0
$pushAttemptedCount = 0
$pushSucceededCount = 0

for ($cycle = 1; $cycle -le $Cycles; $cycle += 1) {
  Write-Host ""
  Write-Host "RAG autonomous cycle $cycle of $Cycles started."

  $pipelineArgs = @{}
  if ($CommitOnPass) { $pipelineArgs.CommitOnPass = $true }
  if ($PushOnPass) { $pipelineArgs.PushOnPass = $true }
  if ($CommitOnPass -and $PSBoundParameters.ContainsKey("CommitMessage") -and -not [string]::IsNullOrWhiteSpace($CommitMessage)) {
    $pipelineArgs.CommitMessage = $CommitMessage
  }

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $pipelineOutput = & $PipelineScript @pipelineArgs *>&1
    $pipelineExitCode = $LASTEXITCODE
  } catch {
    $pipelineOutput = @($_.Exception.Message)
    $pipelineExitCode = 1
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }

  $pipelineOutput | ForEach-Object { Write-Host $_ }
  $pipelineResult = Get-PipelineResult -PipelineOutput $pipelineOutput
  $plannerResult = Get-SummaryValue -PipelineOutput $pipelineOutput -Label "planner result"
  $createdTaskPath = Get-SummaryValue -PipelineOutput $pipelineOutput -Label "planner created task path"
  $completedTaskPath = Get-SummaryValue -PipelineOutput $pipelineOutput -Label "completed task path"
  if ([string]::IsNullOrWhiteSpace($completedTaskPath)) {
    $completedTaskPath = Get-SummaryValue -PipelineOutput $pipelineOutput -Label "completed task"
  }
  if (Test-YesSummaryValue (Get-SummaryValue -PipelineOutput $pipelineOutput -Label "commit attempted")) {
    $commitAttemptedCount += 1
  }
  if (Test-YesSummaryValue (Get-SummaryValue -PipelineOutput $pipelineOutput -Label "commit succeeded")) {
    $commitSucceededCount += 1
  }
  if (Test-YesSummaryValue (Get-SummaryValue -PipelineOutput $pipelineOutput -Label "push attempted")) {
    $pushAttemptedCount += 1
  }
  if (Test-YesSummaryValue (Get-SummaryValue -PipelineOutput $pipelineOutput -Label "push succeeded")) {
    $pushSucceededCount += 1
  }
  if (-not [string]::IsNullOrWhiteSpace($createdTaskPath) -and $createdTaskPath -ne "(none)") {
    $generatedTasks.Add($createdTaskPath)
  }
  if (-not [string]::IsNullOrWhiteSpace($completedTaskPath) -and $completedTaskPath -ne "(none)") {
    $completedTasks.Add($completedTaskPath)
  }
  Write-Host "RAG autonomous cycle $cycle result: $pipelineResult (exit code $pipelineExitCode)"
  $completedCycles += 1

  if ($pipelineExitCode -ne 0) {
    $finalExitCode = $pipelineExitCode
    $stoppedReason = "pipeline exited non-zero in cycle $cycle"
    Write-Host "RAG autonomous loop stopped after cycle $cycle because the pipeline exited non-zero."
    break
  }

  if (Test-StopResult -PipelineResult $pipelineResult) {
    if ($pipelineResult -eq "FAIL") {
      $finalExitCode = 1
    }
    $stoppedReason = "terminal state $pipelineResult in cycle $cycle"
    Write-Host "RAG autonomous loop stopped after cycle $cycle on terminal state $pipelineResult."
    break
  }

  if ($pipelineResult -eq "NO_ACTIONABLE_TASKS" -and $plannerResult -eq "NO_CANDIDATE") {
    $successfulCycles += 1
    $stoppedReason = "no actionable RAG tasks and planner has no candidate"
    Write-Host "RAG autonomous loop stopped after cycle $cycle because planner returned no candidate."
    break
  }

  if (-not (Test-ContinueResult -PipelineResult $pipelineResult)) {
    $finalExitCode = 1
    $stoppedReason = "unknown state $pipelineResult in cycle $cycle"
    Write-Host "RAG autonomous loop stopped after cycle $cycle on unknown state $pipelineResult."
    break
  }

  $successfulCycles += 1
}

Write-OperatorSummary -TotalCycles $Cycles -CompletedCycles $completedCycles -SuccessfulCycles $successfulCycles -StoppedReason $stoppedReason -GeneratedTasks $generatedTasks.ToArray() -CompletedTasks $completedTasks.ToArray() -CommitAttemptedCount $commitAttemptedCount -CommitSucceededCount $commitSucceededCount -PushAttemptedCount $pushAttemptedCount -PushSucceededCount $pushSucceededCount
Write-Host "RAG autonomous loop finished with exit code $finalExitCode."
exit $finalExitCode
