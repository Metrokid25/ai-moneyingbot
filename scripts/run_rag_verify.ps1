[CmdletBinding()]
param(
  [switch]$Help,
  [switch]$SmokeOnly,
  [switch]$KeepArtifacts,
  [string]$WorkDir = ".tmp/rag_e2e_runtime_smoke_verify"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Help) {
  Write-Host @"
run_rag_verify.ps1

Purpose:
  One command to VERIFY the RAG pipeline. Runs the fixture-based end-to-end
  runtime smoke (068) and then the focused RAG test suite, using the project
  .venv Python automatically.

Usage:
  .\scripts\run_rag_verify.ps1
  .\scripts\run_rag_verify.ps1 -SmokeOnly
  .\scripts\run_rag_verify.ps1 -WorkDir .tmp/rag_e2e_runtime_smoke_manual -KeepArtifacts

Options:
  -SmokeOnly       Run only the end-to-end runtime smoke; skip the focused suite.
  -KeepArtifacts   Pass --keep-artifacts to the smoke (reuse the work-dir).
  -WorkDir <path>  Smoke work directory. Must be a safe temporary smoke path.
                   Default: .tmp/rag_e2e_runtime_smoke_verify
  -Help            Print this help only; do not run anything.

Boundary:
  Verification only. This runner uses synthetic fixtures and temporary work-dir
  artifacts. It does NOT run or mutate the production RAG knowledge pipeline
  (060-068 against agent_reports/), does NOT skip the human review gates, and
  does NOT touch Trading Bot files, data/, .env, or archive.db.
  For the real operator pipeline see docs/rag_agent_operator_runbook.md.
"@
  exit 0
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  throw "venv Python not found: $VenvPython. Create it per README (.\.venv) before running verification."
}

$SmokeScript = Join-Path $ScriptDir "run_rag_end_to_end_runtime_smoke.py"
$FocusedScript = Join-Path $ScriptDir "run_rag_focused_tests.py"
if (-not (Test-Path $SmokeScript)) {
  throw "Missing smoke runner: $SmokeScript"
}
if (-not (Test-Path $FocusedScript)) {
  throw "Missing focused test runner: $FocusedScript"
}

function Invoke-VerifyStep {
  param(
    [string]$Title,
    [string[]]$Arguments
  )

  Write-Host ""
  Write-Host "=== $Title ==="
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $VenvPython @Arguments | Out-Host
    $exitCode = $LASTEXITCODE
  } catch {
    Write-Host $_.Exception.Message
    $exitCode = 1
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  return [int]$exitCode
}

$smokeArgs = @("scripts\run_rag_end_to_end_runtime_smoke.py", "--work-dir", $WorkDir)
if ($KeepArtifacts) {
  $smokeArgs += "--keep-artifacts"
}

$smokeExit = Invoke-VerifyStep -Title "End-to-end runtime smoke (068)" -Arguments $smokeArgs

$focusedExit = 0
$focusedRan = $false
if ($SmokeOnly) {
  Write-Host ""
  Write-Host "SmokeOnly requested: focused RAG test suite skipped."
} else {
  $focusedRan = $true
  $focusedExit = Invoke-VerifyStep -Title "Focused RAG test suite" -Arguments @("scripts\run_rag_focused_tests.py")
}

function Format-StepResult {
  param([int]$ExitCode)
  if ($ExitCode -eq 0) { return "PASS" } else { return "FAIL" }
}

$overallExit = 0
if ($smokeExit -ne 0) { $overallExit = $smokeExit }
if ($focusedExit -ne 0 -and $overallExit -eq 0) { $overallExit = $focusedExit }

$result = if ($overallExit -eq 0) { "PASS" } else { "FAIL" }

Write-Host ""
Write-Host "RAG Verify Summary"
Write-Host "smoke result: $(Format-StepResult $smokeExit)"
if ($focusedRan) {
  Write-Host "focused suite result: $(Format-StepResult $focusedExit)"
} else {
  Write-Host "focused suite result: SKIPPED"
}
Write-Host "RAG_VERIFY_RESULT=$result"

exit $overallExit
