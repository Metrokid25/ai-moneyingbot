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

function Test-ContinueResult {
  param([string]$PipelineResult)

  return @("PASS", "PLANNER_CREATED_TASK", "NO_ACTIONABLE_TASKS") -contains $PipelineResult
}

function Test-StopResult {
  param([string]$PipelineResult)

  return @("FAIL", "NEEDS_HUMAN_REVIEW") -contains $PipelineResult
}

Write-Host "Starting RAG autonomous loop for $Cycles cycle(s)."
$finalExitCode = 0

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
  Write-Host "RAG autonomous cycle $cycle result: $pipelineResult (exit code $pipelineExitCode)"

  if ($pipelineExitCode -ne 0) {
    $finalExitCode = $pipelineExitCode
    Write-Host "RAG autonomous loop stopped after cycle $cycle because the pipeline exited non-zero."
    break
  }

  if (Test-StopResult -PipelineResult $pipelineResult) {
    if ($pipelineResult -eq "FAIL") {
      $finalExitCode = 1
    }
    Write-Host "RAG autonomous loop stopped after cycle $cycle on terminal state $pipelineResult."
    break
  }

  if (-not (Test-ContinueResult -PipelineResult $pipelineResult)) {
    $finalExitCode = 1
    Write-Host "RAG autonomous loop stopped after cycle $cycle on unknown state $pipelineResult."
    break
  }
}

Write-Host "RAG autonomous loop finished with exit code $finalExitCode."
exit $finalExitCode
