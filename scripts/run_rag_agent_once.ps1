param(
  [switch]$DryRun,
  [switch]$NoCommit,
  [switch]$NoPush,
  [switch]$UseCodexSandbox,
  [string]$CommitMessagePrefix = "RAG autorunner"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

$ReportDir = Join-Path $RepoRoot "agent_reports"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ReportPath = Join-Path $ReportDir "rag-autorunner-$Timestamp.md"
$CodexLogPath = Join-Path $ReportDir "rag-autorunner-$Timestamp.codex.log"

function Add-Report {
  param([string]$Text)
  Add-Content -Path $ReportPath -Value $Text -Encoding UTF8
}

function Add-ReportCommand {
  param(
    [string]$Title,
    [scriptblock]$Command
  )

  Add-Report ""
  Add-Report "## $Title"
  Add-Report ""
  Add-Report '```text'
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = & $Command 2>&1 | Out-String
    if ([string]::IsNullOrWhiteSpace($output)) {
      Add-Report "(no output)"
    } else {
      Add-Report $output.TrimEnd()
    }
  } catch {
    Add-Report $_.Exception.Message
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
    Add-Report '```'
  }
}

function Get-CurrentBranch {
  return (& git branch --show-current).Trim()
}

function Get-ChangedFiles {
  $lines = & git status --porcelain --untracked-files=all
  $files = New-Object System.Collections.Generic.List[string]
  foreach ($line in $lines) {
    if ([string]::IsNullOrWhiteSpace($line) -or $line.Length -lt 4) {
      continue
    }
    $path = $line.Substring(3).Trim()
    if ($path.Contains(" -> ")) {
      $path = ($path -split " -> ")[-1].Trim()
    }
    $path = $path.Trim('"').Replace("\", "/")
    if (-not [string]::IsNullOrWhiteSpace($path)) {
      $files.Add($path)
    }
  }
  return $files.ToArray()
}

function Test-AllowlistedPath {
  param([string]$Path)

  $p = $Path.Replace("\", "/")
  if ($p.StartsWith("agent_prompts/")) { return $true }
  if ($p.StartsWith("agent_tasks/pending/")) { return $true }
  if ($p.StartsWith("agent_tasks/done/")) { return $true }
  if ($p.StartsWith("agent_tasks/failed/")) { return $true }
  if ($p.StartsWith("agent_reports/")) { return $true }
  if ($p.StartsWith("docs/")) { return $true }
  if ($p.StartsWith("tests/fixtures/")) { return $true }
  if ($p -match '^tests/test_rag_.*\.py$') { return $true }

  $exact = @(
    "scripts/run_rag_agent_once.ps1",
    "scripts/run_rag_agent_loop.ps1",
    "scripts/ingest_archive_export.py",
    "scripts/build_chunks_phase2.py",
    "scripts/load_qdrant_phase2.py",
    "scripts/serve_rag_web.py",
    "scripts/run_rag_focused_tests.py",
    "src/rag_chunking.py",
    "src/rag_qdrant.py",
    "src/rag_retrieval.py",
    "src/rag_answer_context.py",
    "src/rag_answering.py",
    "tests/test_retrieval_eval.py",
    "tests/test_ingest_archive_export.py"
  )
  return $exact -contains $p
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

function Invoke-LoggedProcess {
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

function Invoke-CodexExec {
  param(
    [string]$PromptText,
    [string]$LogPath,
    [switch]$UseCodexSandbox
  )

  $stdoutPath = "$LogPath.stdout.tmp"
  $stderrPath = "$LogPath.stderr.tmp"
  Remove-Item -Path $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue

  try {
    # Primary command for current Codex CLI builds:
    #   codex exec --dangerously-bypass-approvals-and-sandbox -
    # Use -UseCodexSandbox to run the older workspace-write sandbox mode:
    #   codex exec --sandbox workspace-write -
    # The prompt is written to stdin to avoid PowerShell argument quoting issues.
    # The bypass mode is used by default because Windows automatic sessions can
    # fail inside Codex's internal sandbox with "windows sandbox: spawn setup refresh".
    $codexArgs = if ($UseCodexSandbox) {
      @("exec", "--sandbox", "workspace-write", "-")
    } else {
      @("exec", "--dangerously-bypass-approvals-and-sandbox", "-")
    }
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $PromptText | & codex @codexArgs 1> $stdoutPath 2> $stderrPath
    $exitCode = $LASTEXITCODE
  } catch {
    $exitCode = 1
    Set-Content -Path $stderrPath -Value $_.Exception.Message -Encoding UTF8
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
    $stdout = if (Test-Path $stdoutPath) { Get-Content -Path $stdoutPath -Raw -Encoding UTF8 } else { "" }
    $stderr = if (Test-Path $stderrPath) { Get-Content -Path $stderrPath -Raw -Encoding UTF8 } else { "" }
    Set-Content -Path $LogPath -Value "## stdout" -Encoding UTF8
    Add-Content -Path $LogPath -Value $stdout -Encoding UTF8
    Add-Content -Path $LogPath -Value "## stderr" -Encoding UTF8
    Add-Content -Path $LogPath -Value $stderr -Encoding UTF8
    Remove-Item -Path $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
  }

  return $exitCode
}

Set-Content -Path $ReportPath -Value "# RAG Autorunner Report $Timestamp" -Encoding UTF8
Add-Report ""
Add-Report "- DryRun: $DryRun"
Add-Report "- NoCommit: $NoCommit"
Add-Report "- NoPush: $NoPush"
Add-Report "- UseCodexSandbox: $UseCodexSandbox"

$branch = Get-CurrentBranch
$branchAllowsAutomation = $branch -like "agent/rag-*"
$protectedBranch = $branch -in @("main", "master")
$codexSandboxMode = if ($UseCodexSandbox) { "workspace-write" } else { "bypassed" }
Add-Report "- Branch: $branch"
Add-Report "- Branch allows automation: $branchAllowsAutomation"
Add-Report "- Codex sandbox mode: $codexSandboxMode"
if (-not $UseCodexSandbox) {
  Add-Report "- Codex internal sandbox is bypassed for Windows autorunner compatibility."
  Add-Report "- Safety is enforced by the runner safety gate."
}

Add-ReportCommand "Pre-run git status" { git status -sb }
Add-ReportCommand "Pending tasks before run" { python scripts/agent_next_task.py --list }

if (-not (Test-Path "agent_prompts/rag_autorunner.md")) {
  Add-Report ""
  Add-Report "BLOCKED: missing agent_prompts/rag_autorunner.md."
  exit 1
}

$PromptText = Get-Content -Path "agent_prompts/rag_autorunner.md" -Raw -Encoding UTF8
$codexExit = 0
$codexFailed = $false

if ($DryRun) {
  Add-Report ""
  Add-Report "DryRun: skipped codex exec, commit, and push."
} else {
  Add-Report ""
  Add-Report "## codex exec"
  Add-Report ""
  Add-Report "Log: $CodexLogPath"
  Add-Report "Codex sandbox mode: $codexSandboxMode"
  $codexExit = Invoke-CodexExec -PromptText $PromptText -LogPath $CodexLogPath -UseCodexSandbox:$UseCodexSandbox
  Add-Report "codex_exit_code=$codexExit"
  if ($codexExit -ne 0) {
    $codexFailed = $true
    Add-Report "blocked: codex exec failed"
  }
}

Add-ReportCommand "Post-run git status" { git status -sb }
Add-ReportCommand "Post-run git diff stat" { git diff --stat }

$diffCheckExit = Invoke-LoggedProcess "git diff check" "git" @("diff", "--check")
Add-ReportCommand "Pending tasks after run" { python scripts/agent_next_task.py --list }

$pytestExit = Invoke-LoggedProcess "pytest" "pytest" @("--basetemp=.tmp\pytest")
if ($pytestExit -ne 0) {
  Add-Report "pytest failed. Review whether failures are known dependency collection issues or new test failures before trusting automation."
}

$changedFiles = @(Get-ChangedFiles)
Add-Report ""
Add-Report "## Changed files"
if ($changedFiles.Count -eq 0) {
  Add-Report "(none)"
} else {
  foreach ($file in $changedFiles) {
    Add-Report "- $file"
  }
}

$notAllowed = @($changedFiles | Where-Object { -not (Test-AllowlistedPath $_) })
$forbidden = @($changedFiles | Where-Object { Test-ForbiddenPath $_ })

Add-Report ""
Add-Report "## Safety gate"
$canCommit = $true
if ($DryRun) {
  $canCommit = $false
  Add-Report "- blocked: DryRun is enabled."
}
if ($NoCommit) {
  $canCommit = $false
  Add-Report "- blocked: NoCommit is enabled."
}
if (-not $branchAllowsAutomation) {
  $canCommit = $false
  Add-Report "- blocked: branch must start with agent/rag-."
}
if ($protectedBranch) {
  $canCommit = $false
  Add-Report "- blocked: main/master automatic commit is forbidden."
}
if ($changedFiles.Count -eq 0) {
  $canCommit = $false
  Add-Report "- blocked: no changed files."
}
if ($notAllowed.Count -gt 0) {
  $canCommit = $false
  Add-Report "- blocked: files outside allowlist:"
  foreach ($file in $notAllowed) { Add-Report "  - $file" }
}
if ($forbidden.Count -gt 0) {
  $canCommit = $false
  Add-Report "- blocked: forbidden files changed:"
  foreach ($file in $forbidden) { Add-Report "  - $file" }
}
if ($diffCheckExit -ne 0) {
  $canCommit = $false
  Add-Report "- blocked: git diff --check failed."
}
if ($codexFailed) {
  $canCommit = $false
  Add-Report "- blocked: codex exec failed"
}

if ($canCommit) {
  Add-Report "- passed: automatic commit safety gate."
  foreach ($file in $changedFiles) {
    git add -- $file
  }
  $commitMessage = "${CommitMessagePrefix}: $Timestamp"
  git commit -m $commitMessage
  $commitExit = $LASTEXITCODE
  Add-Report "- commit exit code: $commitExit"
  if ($commitExit -ne 0) {
    Add-Report "BLOCKED: git commit failed."
    exit $commitExit
  }

  if ($NoPush) {
    Add-Report "- push skipped: NoPush is enabled."
  } elseif ($protectedBranch) {
    Add-Report "BLOCKED: main/master automatic push is forbidden."
    exit 1
  } else {
    git push -u origin $branch
    $pushExit = $LASTEXITCODE
    Add-Report "- push target: origin/$branch"
    Add-Report "- push exit code: $pushExit"
    if ($pushExit -ne 0) {
      Add-Report "BLOCKED: git push failed."
      exit $pushExit
    }
  }
} else {
  Add-Report "- result: no automatic commit or push."
}

Add-Report ""
Add-Report "Report written to $ReportPath"
Write-Host "Report written to $ReportPath"
