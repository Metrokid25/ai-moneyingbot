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
      if ($text -match "^REVIEW_RESULT=(PASS|FAIL|NEEDS_HUMAN_REVIEW)$") {
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

function Invoke-PassGatedPublish {
  param(
    [string]$Message,
    [switch]$Commit,
    [switch]$Push
  )

  if (-not $Commit) {
    if ($Push) {
      Write-Host "PushOnPass requested without CommitOnPass. No push will run without a successful pass-gated commit."
    }
    Write-Host "Pipeline passed review. Waiting for user approval before any commit or push."
    return 0
  }

  $changedPaths = @(Get-ChangedPaths)
  if ($changedPaths.Count -eq 0) {
    Write-Host "Publish gate failed: no changed files to commit."
    return 1
  }

  $forbiddenPaths = @($changedPaths | Where-Object { Test-ForbiddenPublishPath $_ })
  if ($forbiddenPaths.Count -gt 0) {
    Write-Host "Publish gate failed: forbidden files changed."
    foreach ($path in $forbiddenPaths) {
      Write-Host "Forbidden changed file: $path"
    }
    return 1
  }

  Write-Host "Publish gate passed. Staging git status changed files only."
  foreach ($path in $changedPaths) {
    $addExit = Invoke-GitPublishCommand -FailureContext "git add for $path" -Arguments @("add", "--", $path)
    if ($addExit -ne 0) {
      return $addExit
    }
  }

  $commitExit = Invoke-GitPublishCommand -FailureContext "git commit" -Arguments @("commit", "-m", $Message)
  if ($commitExit -ne 0) {
    return $commitExit
  }

  if (-not $Push) {
    Write-Host "Pass-gated commit completed. PushOnPass not requested; push skipped."
    return 0
  }

  $pushExit = Invoke-GitPublishCommand -FailureContext "git push" -Arguments @("push")
  if ($pushExit -ne 0) {
    return $pushExit
  }

  Write-Host "Pass-gated push completed."
  return 0
}

Write-Host "Starting RAG agent pipeline."
Write-Host "Step 1: run_rag_agent_once.ps1 -NoPush"
& $OnceScript -NoPush
$runExit = $LASTEXITCODE
if ($runExit -ne 0) {
  Write-Host "RAG implementation step failed with exit code $runExit."
  exit $runExit
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
  exit 1
}

if ($reviewResult -eq "PASS") {
  $publishExit = Invoke-PassGatedPublish -Message $CommitMessage -Commit:$CommitOnPass -Push:$PushOnPass
  exit $publishExit
} else {
  Write-Host "Pipeline needs human review. Waiting for user approval before any commit or push."
}

exit 0
