param(
    [int]$Hours = 24,
    [int]$MaxCycles = 50,
    [int]$SleepMinutes = 3,
    [string]$Branch = "archive-agent-auto",
    [switch]$PlanOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Repo = "C:\projects\naver_cafe_archive"
Set-Location $Repo

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . ".\.venv\Scripts\Activate.ps1"
}

$LogDir = Join-Path $Repo "agent_reports\auto_logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Run-Cmd {
    param([string]$Command)

    Write-Host ""
    Write-Host ">>> $Command" -ForegroundColor Cyan
    cmd /c $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Command"
    }
}

function Get-ChangedPaths {
    $lines = git status --porcelain
    $paths = @()

    foreach ($line in $lines) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $path = $line.Substring(3).Trim()

        if ($path -eq "scripts/_step3_verify_v2.py") {
            continue
        }

        $paths += $path
    }

    return $paths
}

function Test-AllowedPath {
    param([string]$Path)

    $normalized = $Path.Replace("\", "/")

    if ($normalized -eq "scripts/daily_archive.py") { return $true }
    if ($normalized -eq "scripts/index_tail.py") { return $true }
    if ($normalized -eq "scripts/batch_recollect.py") { return $true }
    if ($normalized -eq "scripts/run_archive_agent_loop.ps1") { return $true }

    if ($normalized -eq "src/browser.py") { return $true }
    if ($normalized -eq "src/parser.py") { return $true }
    if ($normalized -eq "src/db.py") { return $true }
    if ($normalized -eq "src/collector.py") { return $true }
    if ($normalized -eq "src/indexer.py") { return $true }
    if ($normalized -eq "src/models.py") { return $true }
    if ($normalized -eq "src/config.py") { return $true }

    if ($normalized -eq "tests/test_daily_archive.py") { return $true }
    if ($normalized -like "tests/*archive*.py") { return $true }

    if ($normalized -like "agent_tasks/pending/*") { return $true }
    if ($normalized -like "agent_reports/*") { return $true }
    if ($normalized -eq "agent_prompts/archive_builder.md") { return $true }

    return $false
}

function Assert-NoForbiddenChanges {
    $changed = Get-ChangedPaths

    $forbidden = @()
    foreach ($path in $changed) {
        if (-not (Test-AllowedPath $path)) {
            $forbidden += $path
        }
    }

    if ($forbidden.Count -gt 0) {
        Write-Host ""
        Write-Host "Forbidden changes detected. Auto loop stopped." -ForegroundColor Red
        $forbidden | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
        throw "Forbidden file changes detected"
    }
}

function Invoke-ArchiveAgentCycle {
    param([int]$Cycle)

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $logPath = Join-Path $LogDir "archive-agent-cycle-$timestamp.log"

    $Prompt = @"
You are the Archive Bot / Naver Cafe Archive Bot automation agent.
Write all reports in English only to avoid Windows console encoding issues.
Do not use Korean in generated markdown reports.

작업 폴더:
C:\projects\naver_cafe_archive

현재 모드:
24시간 자동 개발 루프의 단일 사이클이다.
이번 사이클은 PLAN-ONLY 안전 점검 모드다.
pending task 하나를 읽고, 구현하지 말고 작업 계획만 작성한다.

목표:
scripts/agent_next_task.py로 다음 pending task를 확인하고,
agent_prompts/archive_builder.md 원칙에 따라 Archive 작업 계획만 작성한다.
실제 코드 수정은 하지 않는다.

반드시 먼저 확인:
1. git status -sb
2. python scripts/agent_next_task.py
3. agent_prompts/archive_builder.md
4. 선택된 agent_tasks/pending 작업 파일

수정 허용:
- scripts/daily_archive.py
- scripts/index_tail.py
- scripts/batch_recollect.py
- src/browser.py
- src/parser.py
- src/db.py
- src/collector.py
- src/indexer.py
- src/models.py
- src/config.py
- tests/test_daily_archive.py
- archive 관련 tests
- agent_tasks/pending/archive 관련 작업
- agent_prompts/archive_builder.md
- agent_reports/ 새 보고서

수정 금지:
- src/rag_*
- scripts/answer_question_phase2.py
- scripts/build_chunks_phase2.py
- scripts/embed_chunks_phase2.py
- scripts/load_qdrant_phase2.py
- scripts/serve_rag_web.py
- RAG vector index 관련 파일
- RAG web UI 관련 파일
- .env
- archive.db
- data/
- scripts/_step3_verify_v2.py

절대 금지:
- git add .
- 커밋 금지
- 푸시 금지
- archive.db 삭제/초기화 금지
- data 삭제 금지
- .env 수정 금지
- scripts/_step3_verify_v2.py 수정 금지
- 무제한 실제 수집 금지
- 실제 네이버카페 접속 임의 실행 금지
- 테스트에서 외부 네트워크 요청 금지

중요:
커밋과 푸시는 네가 하지 마라.
이 루프 스크립트가 테스트와 파일 안전검사를 통과한 뒤 자동으로 처리한다.

작업 방식:
1. pending task 하나만 선택한다.
2. 실제 코드 수정은 절대 하지 않는다.
3. 테스트 파일도 수정하지 않는다.
4. agent_reports/에 markdown 계획 보고서만 작성한다.
5. 계획 보고서에는 작업 목표, 수정 예상 파일, 금지 파일, 테스트 계획, 위험 요소, 예상 커밋 단위를 포함한다.
6. 실제 네이버카페 접속이 필요한 명령은 실행하지 않는다.
7. 할 pending task가 없으면 새 작업을 만들지 말고 보고서에 할 일이 없다고 남긴다.

필수 검증:
git status -sb
git diff --stat

이번 PLAN-ONLY 모드에서는 pytest와 daily_archive 실행은 하지 않는다.

실제 수집 명령은 실행하지 말고 필요 여부만 보고:
python scripts/daily_archive.py --execute --limit 2 --list-url "<URL>"

보고서에는 반드시 포함:
1. 선택한 pending task
2. 구현 계획
3. 수정 예상 파일
4. 수정 금지 파일
5. 테스트 계획
6. 위험 요소
7. 예상 커밋 단위
8. 실제 수집 필요 여부
9. 실제 코드 수정하지 않았는지 확인
10. git status -sb
11. git diff --stat

지금 바로 이번 사이클 작업을 시작해라.
"@

    Write-Host ""
    Write-Host "========== Archive Agent Cycle $Cycle ==========" -ForegroundColor Green

    $promptPath = Join-Path $LogDir "archive-agent-prompt-$timestamp.txt"
    $stdoutPath = Join-Path $LogDir "archive-agent-stdout-$timestamp.log"
    $stderrPath = Join-Path $LogDir "archive-agent-stderr-$timestamp.log"

    Set-Content -Encoding UTF8 $promptPath $Prompt

    $codexCommand = "codex exec --cd `"$Repo`" --sandbox workspace-write - < `"$promptPath`" > `"$stdoutPath`" 2> `"$stderrPath`""
    cmd /c $codexCommand
    $codexExitCode = $LASTEXITCODE

    $combinedOutput = @()

    if (Test-Path $stdoutPath) {
        $combinedOutput += Get-Content $stdoutPath
    }

    if (Test-Path $stderrPath) {
        $combinedOutput += Get-Content $stderrPath
    }

    $combinedOutput | Tee-Object -FilePath $logPath

    if ($codexExitCode -ne 0) {
        throw "Codex exec failed with exit code $codexExitCode. See log: $logPath"
    }

    Assert-NoForbiddenChanges

    if ($PlanOnly) {
        Write-Host "PLAN-ONLY mode: skipping pytest and daily_archive runtime checks."
        Run-Cmd "git status -sb"
        Run-Cmd "git diff --stat"
    }
    else {
        Run-Cmd "pytest --basetemp=.tmp\pytest"
        Run-Cmd "python scripts\daily_archive.py --dry-run"
        Run-Cmd "python scripts\daily_archive.py"
    }

    Assert-NoForbiddenChanges

    $changed = Get-ChangedPaths

    if ($changed.Count -eq 0) {
        Write-Host "No commit-worthy changes in this cycle."
        return
    }

    Write-Host ""
    Write-Host "Allowed changed files:" -ForegroundColor Yellow
    $changed | ForEach-Object { Write-Host " - $_" }

    foreach ($path in $changed) {
        Run-Cmd "git add -- `"$path`""
    }

    Run-Cmd "git diff --cached --stat"

    $staged = git diff --cached --name-only
    if ([string]::IsNullOrWhiteSpace(($staged -join ""))) {
        Write-Host "No staged changes. Skipping commit."
        return
    }

    $commitMessage = "Archive agent auto cycle $timestamp"
    Run-Cmd "git commit -m `"$commitMessage`""
    Run-Cmd "git push -u origin $Branch"

    Write-Host ""
    Write-Host "Cycle $Cycle committed and pushed: $commitMessage" -ForegroundColor Green
}

Write-Host "Preparing archive auto branch: $Branch" -ForegroundColor Green

Run-Cmd "git status -sb"
Assert-NoForbiddenChanges

Run-Cmd "git fetch origin"
Run-Cmd "git checkout main"
Run-Cmd "git pull --ff-only"

$remoteBranch = git ls-remote --heads origin $Branch
if (-not [string]::IsNullOrWhiteSpace($remoteBranch)) {
    Run-Cmd "git checkout $Branch"
    Run-Cmd "git pull --ff-only"
}
else {
    Run-Cmd "git checkout -B $Branch"
}

$stopAt = (Get-Date).AddHours($Hours)
$cycle = 1

while ((Get-Date) -lt $stopAt -and $cycle -le $MaxCycles) {
    try {
        Invoke-ArchiveAgentCycle -Cycle $cycle
    }
    catch {
        $errorPath = Join-Path $LogDir ("archive-agent-error-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
        $_ | Out-File -Encoding UTF8 $errorPath

        Write-Host ""
        Write-Host "Archive auto loop stopped because of an error." -ForegroundColor Red
        Write-Host "Error log: $errorPath" -ForegroundColor Red
        throw
    }

    $cycle += 1

    if ((Get-Date) -lt $stopAt -and $cycle -le $MaxCycles) {
        Write-Host ""
        Write-Host "Sleeping $SleepMinutes minutes before next cycle..."
        Start-Sleep -Seconds ($SleepMinutes * 60)
    }
}

Write-Host ""
Write-Host "Archive auto loop finished." -ForegroundColor Green
Run-Cmd "git status -sb"
Run-Cmd "git log --oneline -10"




