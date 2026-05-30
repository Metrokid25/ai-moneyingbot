param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

$ReportDir = Join-Path $RepoRoot "agent_reports"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ReportPath = Join-Path $ReportDir "rag-review-$Timestamp.md"

function Add-Report {
  param([string]$Text)
  Add-Content -Path $ReportPath -Value $Text -Encoding UTF8
}

function Invoke-ReviewCommand {
  param(
    [string]$Title,
    [string]$FilePath,
    [string[]]$Arguments
  )

  Add-Report ""
  Add-Report "## $Title"
  Add-Report ""
  Add-Report '```text'
  Add-Report "$FilePath $($Arguments -join ' ')"

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = & $FilePath @Arguments 2>&1 | Out-String
    $exitCode = $LASTEXITCODE
    if (-not [string]::IsNullOrWhiteSpace($output)) {
      Add-Report $output.TrimEnd()
    }
  } catch {
    $exitCode = 1
    Add-Report $_.Exception.Message
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }

  Add-Report "exit_code=$exitCode"
  Add-Report '```'
  return $exitCode
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

function Test-ForbiddenPath {
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
    "src/indexer.py"
  )

  if ($forbiddenExact -contains $p) { return $true }
  if ($p.StartsWith("data/")) { return $true }
  return $false
}

function Get-TaskMovementNotes {
  param([string[]]$ChangedPaths)

  $notes = New-Object System.Collections.Generic.List[string]
  $taskPaths = @($ChangedPaths | Where-Object {
    $_.StartsWith("agent_tasks/pending/") -or $_.StartsWith("agent_tasks/done/")
  })

  if ($taskPaths.Count -eq 0) {
    $notes.Add("No pending/done task movement detected.")
  } else {
    foreach ($path in $taskPaths) {
      $notes.Add($path)
    }
  }
  return $notes.ToArray()
}

Set-Content -Path $ReportPath -Value "# RAG Review Report $Timestamp" -Encoding UTF8
Add-Report ""
Add-Report "Review script mode: read-only"
Add-Report "Repository: $RepoRoot"

$statusExit = Invoke-ReviewCommand "git status -sb" "git" @("status", "-sb")
$diffNameExit = Invoke-ReviewCommand "git diff --name-only" "git" @("diff", "--name-only")
$diffStatExit = Invoke-ReviewCommand "git diff --stat" "git" @("diff", "--stat")
$diffCheckExit = Invoke-ReviewCommand "git diff --check" "git" @("diff", "--check")
$focusedExit = Invoke-ReviewCommand "RAG focused tests" "python" @("scripts\run_rag_focused_tests.py")
$tasksExit = Invoke-ReviewCommand "agent task list" "python" @("scripts\agent_next_task.py", "--list")

$changedPaths = @(Get-ChangedPaths)
$forbiddenPaths = @($changedPaths | Where-Object { Test-ForbiddenPath $_ })
$archiveTaskPath = "agent_tasks/pending/001-real-daily-archive-wiring.md"
$archiveTaskChanged = $changedPaths -contains $archiveTaskPath
$taskMovementNotes = @(Get-TaskMovementNotes -ChangedPaths $changedPaths)

Add-Report ""
Add-Report "## Changed paths from status"
if ($changedPaths.Count -eq 0) {
  Add-Report "(none)"
} else {
  foreach ($path in $changedPaths) {
    Add-Report "- $path"
  }
}

Add-Report ""
Add-Report "## Forbidden file check"
if ($forbiddenPaths.Count -eq 0) {
  Add-Report "No forbidden files changed."
} else {
  foreach ($path in $forbiddenPaths) {
    Add-Report "- $path"
  }
}

Add-Report ""
Add-Report "## Archive-owned task check"
if ($archiveTaskChanged) {
  Add-Report "Changed: $archiveTaskPath"
} else {
  Add-Report "Not changed: $archiveTaskPath"
}

Add-Report ""
Add-Report "## Pending/done task movement"
foreach ($note in $taskMovementNotes) {
  Add-Report "- $note"
}

$decision = "PASS"
$reasons = New-Object System.Collections.Generic.List[string]

if ($diffCheckExit -ne 0) {
  $decision = "FAIL"
  $reasons.Add("git diff --check failed")
}
if ($focusedExit -ne 0) {
  $decision = "FAIL"
  $reasons.Add("RAG focused tests failed")
}
if ($forbiddenPaths.Count -gt 0) {
  $decision = "FAIL"
  $reasons.Add("forbidden files changed")
}
if ($archiveTaskChanged) {
  $decision = "FAIL"
  $reasons.Add("Archive-owned 001 task changed")
}
if ($decision -ne "FAIL" -and $changedPaths.Count -eq 0) {
  $decision = "NEEDS_HUMAN_REVIEW"
  $reasons.Add("no changed files to review")
}
if ($decision -ne "FAIL" -and ($statusExit -ne 0 -or $diffNameExit -ne 0 -or $diffStatExit -ne 0 -or $tasksExit -ne 0)) {
  $decision = "NEEDS_HUMAN_REVIEW"
  $reasons.Add("one or more informational review commands failed")
}

Add-Report ""
Add-Report "## Decision"
Add-Report "Decision: $decision"
if ($reasons.Count -eq 0) {
  Add-Report "Reasons: checks passed"
} else {
  Add-Report "Reasons:"
  foreach ($reason in $reasons) {
    Add-Report "- $reason"
  }
}
Add-Report ""
Add-Report "Report path: $ReportPath"

Write-Host "REVIEW_RESULT=$decision"
Write-Host "REVIEW_REPORT=$ReportPath"

if ($decision -eq "FAIL") {
  exit 1
}
exit 0
