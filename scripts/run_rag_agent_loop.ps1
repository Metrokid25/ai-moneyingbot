param(
  [int]$Iterations = 1,
  [int]$SleepSeconds = 300,
  [switch]$Forever,
  [switch]$DryRun,
  [switch]$NoCommit,
  [switch]$NoPush
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OnceScript = Join-Path $ScriptDir "run_rag_agent_once.ps1"

if (-not (Test-Path $OnceScript)) {
  throw "Missing once runner: $OnceScript"
}

if (-not $Forever -and $Iterations -lt 1) {
  throw "Iterations must be at least 1 unless -Forever is supplied."
}

$run = 0
while ($Forever -or $run -lt $Iterations) {
  $run += 1
  Write-Host "RAG autorunner iteration $run started."

  $argsForOnce = @()
  if ($DryRun) { $argsForOnce += "-DryRun" }
  if ($NoCommit) { $argsForOnce += "-NoCommit" }
  if ($NoPush) { $argsForOnce += "-NoPush" }

  & $OnceScript @argsForOnce
  $exitCode = $LASTEXITCODE
  if ($exitCode -ne 0) {
    Write-Host "RAG autorunner iteration $run failed with exit code $exitCode. See agent_reports/ for details."
  } else {
    Write-Host "RAG autorunner iteration $run finished."
  }

  if (-not $Forever -and $run -ge $Iterations) {
    break
  }

  Write-Host "Waiting $SleepSeconds seconds before the next iteration."
  Start-Sleep -Seconds $SleepSeconds
}
