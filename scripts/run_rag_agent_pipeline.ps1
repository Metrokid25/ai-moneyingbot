param()

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

Write-Host "Starting RAG agent pipeline."
Write-Host "Step 1: run_rag_agent_once.ps1 -NoPush"
& $OnceScript -NoPush
$runExit = $LASTEXITCODE
if ($runExit -ne 0) {
  Write-Host "RAG implementation step failed with exit code $runExit."
  exit $runExit
}

Write-Host "Step 2: review_rag_agent_run.ps1"
$reviewOutput = & $ReviewScript 2>&1
$reviewExit = $LASTEXITCODE
$reviewOutput | ForEach-Object { Write-Host $_ }

$reviewResult = "UNKNOWN"
$reviewReport = ""
foreach ($line in $reviewOutput) {
  $text = [string]$line
  if ($text.StartsWith("REVIEW_RESULT=")) {
    $reviewResult = $text.Substring("REVIEW_RESULT=".Length)
  }
  if ($text.StartsWith("REVIEW_REPORT=")) {
    $reviewReport = $text.Substring("REVIEW_REPORT=".Length)
  }
}

Write-Host "Pipeline review result: $reviewResult"
if (-not [string]::IsNullOrWhiteSpace($reviewReport)) {
  Write-Host "Pipeline review report: $reviewReport"
}

if ($reviewExit -ne 0 -or $reviewResult -eq "FAIL") {
  Write-Host "Pipeline stopped after review failure. Inspect the review report before continuing."
  exit 1
}

if ($reviewResult -eq "PASS") {
  Write-Host "Pipeline passed review. Waiting for user approval before any commit or push."
} else {
  Write-Host "Pipeline needs human review. Waiting for user approval before any commit or push."
}

exit 0
