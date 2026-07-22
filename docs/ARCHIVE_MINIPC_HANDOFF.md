# Archive봇 미니PC pull 기반 인수인계

> 미니PC Archive 담당자의 **현재 작업 정본**이다. 채팅 프롬프트나 별도 txt 파일을 전달받지 않는다.
> 저장소 `main`을 안전하게 갱신한 뒤 이 문서와 `docs/ARCHIVE_MINIPC_OPERATIONS.md`만 따라 작업한다.
> 고정 해시를 최신이라고 가정하지 말고 항상 `git fetch origin` 후 `origin/main`을 권위값으로 사용한다.

## 1. 이번 작업 목표

Archive index-tail 포크 통합 커밋 `d8c806c` 이상을 미니PC에 반영하고, 실행 중인
`Archive-CollectLoop`를 안전 재시작한 뒤 통합 healthcheck로 라이브 정상 여부를 검증한다.

- `scripts/index_tail.py`: 수동·실시간 수집의 단일 정본
- `scripts/index_tail_realtime.py`: 기존 실행/import 경로만 보존하는 호환 shim
- 무인 루프: `index_tail.run_realtime_index`를 직접 import

## 2. Git 갱신 — 사용자 변경 보존

```powershell
cd C:\projects\naver_cafe_archive
git status --short --branch
$trackedDirty = @(git status --porcelain=v1 --untracked-files=no)
if ($LASTEXITCODE -ne 0) { throw "git status failed" }
if ($trackedDirty.Count -ne 0) { throw "tracked or staged changes exist; do not update" }
git fetch origin
if ($LASTEXITCODE -ne 0) { throw "git fetch origin failed" }
git rev-parse HEAD
git rev-parse origin/main
```

다음 조건을 먼저 확인한다.

- tracked 수정이나 staged 변경이 있으면 pull/merge/reset/clean/stash를 하지 말고 파일 목록을 보고한다.
- 미추적 `scripts/_step3_verify_v2.py`는 알려진 보존 대상이다. 삭제·수정·스테이징하지 않는다.
- `git add -A`, `git clean`, `git reset --hard`, force push 금지.

tracked 변경이 없을 때만 main을 fast-forward한다.

```powershell
$trackedDirty = @(git status --porcelain=v1 --untracked-files=no)
if ($LASTEXITCODE -ne 0 -or $trackedDirty.Count -ne 0) {
    throw "tracked or staged changes exist; do not switch or merge"
}
git switch main
if ($LASTEXITCODE -ne 0) { throw "git switch main failed" }
git merge --ff-only origin/main
if ($LASTEXITCODE -ne 0) { throw "ff-only update failed" }
$head = (git rev-parse HEAD).Trim()
$originMain = (git rev-parse origin/main).Trim()
if ($head -ne $originMain) { throw "HEAD ($head) does not exactly match origin/main ($originMain)" }
git merge-base --is-ancestor d8c806c HEAD
if ($LASTEXITCODE -ne 0) { throw "Archive deploy commit d8c806c is not included in HEAD" }
git status --short --branch
```

그다음 `docs/ARCHIVE_MINIPC_OPERATIONS.md`의 §2, §4, §5를 읽고 실제 코드와 대조한다.

## 3. 배포 전 기준선

아래 진단은 애플리케이션 DB·태스크·프로세스를 바꾸지 않는 논리적 읽기 전용이다.

```powershell
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe scripts\archive_healthcheck.py --observe-seconds 60
$beforeRc = $LASTEXITCODE
Write-Host "archive_healthcheck_before_rc=$beforeRc"
if ($beforeRc -ne 0) { throw "Pre-deploy Archive healthcheck failed; do not restart" }
```

배포 전 결과가 `HEALTHY`, 종료코드 `0`인지 기록한다. 아니라면 재시작하지 말고 첫 오류를 보고한다.

## 4. CollectLoop 안전 재시작

Archive 운영 코드의 import 대상이 바뀌었으므로 재시작이 필수다. 다른 Python 작업을 보호한다.

```powershell
$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path ".").Path
$profilePattern = [regex]::Escape((Join-Path $projectRoot "state\browser_profile"))
$watchdog = Get-ScheduledTask -TaskName "Archive-Watchdog"
$watchdogWasEnabled = [bool]$watchdog.Settings.Enabled

try {
    # 수동 maintenance와 hourly watchdog의 동시 재시작 경쟁을 차단한다.
    if ($watchdogWasEnabled) {
        Disable-ScheduledTask -TaskName "Archive-Watchdog" | Out-Null
    }
    Stop-ScheduledTask -TaskName "Archive-Watchdog" -ErrorAction Stop
    Start-Sleep -Seconds 2
    $watchdogState = (Get-ScheduledTask -TaskName "Archive-Watchdog").State
    $watchdogProcesses = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -in @("powershell.exe", "pwsh.exe") -and
            $_.CommandLine -and
            $_.CommandLine -match 'archive_watchdog\.ps1'
        }
    )
    if ($watchdogState -eq "Running" -or $watchdogProcesses.Count -ne 0) {
        throw "Archive-Watchdog did not stop cleanly; abort maintenance"
    }

    # Stop 전에 자식 트리를 캡처해야 orphan Chrome도 Archive 소유로 식별할 수 있다.
    $allBefore = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $archivePythonBefore = @(
        $allBefore | Where-Object {
            $_.Name -in @("python.exe", "pythonw.exe") -and
            $_.CommandLine -and
            ($_.CommandLine -match 'run_daily_archive_loop|index_tail_realtime|batch_recollect')
        }
    )
    $archiveTreeIds = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($proc in $archivePythonBefore) {
        $null = $archiveTreeIds.Add([int]$proc.ProcessId)
    }
    do {
        $added = $false
        foreach ($proc in $allBefore) {
            if ($archiveTreeIds.Contains([int]$proc.ParentProcessId) -and
                $archiveTreeIds.Add([int]$proc.ProcessId)) {
                $added = $true
            }
        }
    } while ($added)

    Stop-ScheduledTask -TaskName "Archive-CollectLoop"
    Start-Sleep -Seconds 5

    $residualArchivePython = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -in @("python.exe", "pythonw.exe") -and
            $_.CommandLine -and
            ($_.CommandLine -match 'run_daily_archive_loop|index_tail_realtime|batch_recollect')
        }
    )
    $archiveChrome = @(
        Get-CimInstance Win32_Process -Filter "Name='chrome-headless-shell.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $archiveTreeIds.Contains([int]$_.ProcessId) -or
            ($_.CommandLine -and $_.CommandLine -match $profilePattern)
        }
    )

    $residualArchivePython | Select-Object ProcessId, ParentProcessId, Name, CommandLine
    $archiveChrome | Select-Object ProcessId, ParentProcessId, Name, CommandLine
    foreach ($proc in @($residualArchivePython) + @($archiveChrome)) {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2

    $stillRunning = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -in @("python.exe", "pythonw.exe") -and
            $_.CommandLine -and
            ($_.CommandLine -match 'run_daily_archive_loop|index_tail_realtime|batch_recollect')
        }
    )
    if ($stillRunning.Count -ne 0) { throw "Archive Python remains after targeted cleanup" }

    if ((Get-ScheduledTask -TaskName "Archive-CollectLoop").State -ne "Running") {
        Start-ScheduledTask -TaskName "Archive-CollectLoop"
    }
    Start-Sleep -Seconds 10
}
finally {
    if ($watchdogWasEnabled) {
        Enable-ScheduledTask -TaskName "Archive-Watchdog" | Out-Null
    }
}
```

위 블록은 한 PowerShell 세션에서 통째로 실행한다. 모든 Python/Chrome을 이름만으로 종료하는 명령은 금지한다.
선택된 Archive PID와 Archive browser profile을 쓰는 Chrome만 종료한다.
RAG 색인·요약을 포함한 다른 Python은 종료하지 않는다.

## 5. 배포 후 라이브 검증

```powershell
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe scripts\archive_healthcheck.py --observe-seconds 60
$afterRc = $LASTEXITCODE
Write-Host "archive_healthcheck_after_rc=$afterRc"
if ($afterRc -ne 0) { throw "Post-deploy Archive healthcheck failed" }
```

합격 기준은 전부 만족해야 한다.

- 최종 판정 `HEALTHY`, 종료코드 `0`
- Git HEAD가 `d8c806c`를 포함
- `Archive-CollectLoop`가 `Running`
- `Archive-Watchdog`, `Archive-DailySummary` 정상
- controller instance 정확히 1개
- loop lock 정상
- session alert 없음
- 최근 정상 cycle 또는 catch-up 중 실제 DB/WAL 활동 확인
- 새로운 로그인 차단·DB 오류·반복 재시작 없음

실패하면 반복 재시작, lock 삭제, 브라우저 프로필 조작, 재로그인을 하지 않는다. 첫 실패의 healthcheck 항목과
관련 로그 시각만 보고한다. 쿠키·토큰·Authorization 원문은 출력하지 않는다.

## 6. 보고 형식

1. `HEAD`, `origin/main`, `d8c806c` 포함 여부
2. 배포 전 healthcheck 판정·종료코드
3. 재시작 전후 CollectLoop 상태
4. 잔여 Archive PID 정리 여부(다른 Python 미종료 확인)
5. 배포 후 healthcheck 판정·종료코드
6. controller instance 수
7. max article id 전후와 DB/WAL 활동
8. 최근 cycle return code와 세션 상태
9. 최종 결론: `LIVE VERIFIED` 또는 `NEEDS ATTENTION`

## 7. 라이브 검증 완료 후

`LIVE VERIFIED`면 코드나 문서를 추가 수정하지 말고 결과만 보고한다. 다음 개발 후보는
`find_tail`/`_create_snapshot`의 일시 오류 분류 개선이며, 별도 지시 전에는 시작하지 않는다.
