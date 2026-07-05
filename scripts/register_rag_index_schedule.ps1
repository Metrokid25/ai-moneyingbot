<#
.SYNOPSIS
  Register the daily RAG incremental-index task in Windows Task Scheduler.

.DESCRIPTION
  Runs scripts/run_rag_incremental_notify.py via the project venv once a day
  (default 16:30 local time = after KRX close). Unattended: embeds new chunks
  into Qdrant and reports the result to the RAG Telegram channel.

  Re-running this script updates the existing task (idempotent).

.EXAMPLE
  .\scripts\register_rag_index_schedule.ps1 -DbPath "C:\projects\naver_cafe_archive\data\archive.db"

.NOTES
  Run in a normal (non-elevated) PowerShell. The task runs as the current user
  with LogonType S4U, so it runs even when logged off (headless mini-PC) — there
  is NO interactive-login environment to inherit. The wrapper loads .env itself
  from an absolute path, and paths are resolved absolutely, so this is fine.
  S4U requires the account to hold the "Log on as a batch job" right; if the
  task registers but won't start (LastTaskResult 0x2 / logon failure), grant it
  (see docs/DEPLOY_MINIPC.md troubleshooting).
#>
param(
  [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
  [string]$Time        = "16:30",
  [string]$DbPath      = "",
  [string]$QdrantPath  = "",
  [string]$Collection  = "",
  [string]$TaskName    = "RAG-IncrementalIndex"
)

$ErrorActionPreference = "Stop"

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$script = Join-Path $ProjectRoot "scripts\run_rag_incremental_notify.py"

if (-not (Test-Path $python)) { throw "venv python not found: $python (create .venv first)" }
if (-not (Test-Path $script)) { throw "wrapper not found: $script" }

# Build the argument list for the wrapper.
$argList = @("`"$script`"")
if ($DbPath)     { $argList += @("--db-path", "`"$DbPath`"") }
if ($QdrantPath) { $argList += @("--qdrant-path", "`"$QdrantPath`"") }
if ($Collection) { $argList += @("--collection", "`"$Collection`"") }
$arguments = $argList -join " "

$action    = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $ProjectRoot
$trigger   = New-ScheduledTaskTrigger -Daily -At $Time
# No -RunOnlyIfNetworkAvailable: a transient network check must not silently skip
# the run. If the network is down the wrapper runs, fails, and reports it.
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable `
             -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
# LogonType S4U: runs whether or not the user is interactively logged in (the
# mini-PC is headless / logged off), without storing a password. It can reach
# outbound internet (Voyage, Telegram) but not authenticated network shares,
# which this task does not need.
# Qualify the user as ".\<name>" so a bare username can't misresolve on a
# renamed/domain-joined machine (standalone mini-PC: ".\" = the local account).
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "[OK] Registered scheduled task '$TaskName'"
Write-Host "     runs daily at $Time :  $python $arguments"
Write-Host "     verify:  Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "     run now: Start-ScheduledTask -TaskName '$TaskName'"
