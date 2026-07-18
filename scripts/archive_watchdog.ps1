# Archive 수집 봇 워치독 — 1시간마다 실행. Archive-CollectLoop가 죽었으면 안전하게 재기동.
#
# 안전장치:
#  - State를 간격 두고 두 번 확인해 '재기동 중/일시 Ready'를 죽음으로 오판하지 않음(TOCTOU 완화).
#  - 이 루프의 python만 명령줄로 특정해 정리한다(RAG 색인/일일요약 python은 안 건드림).
#  - 부팅 런처가 lock을 무조건 삭제하므로, 재기동 전 잔여 루프 python을 반드시 제거해
#    이중 인스턴스(SQLite 잠금/브라우저 프로필 충돌)를 방지한다.
$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir "watchdog.log"

function Write-WdLog([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logFile -Value "$ts [watchdog] $msg"
    try {  # 로테이션: 2000줄 초과 시 마지막 1000줄만 유지(무한 증가 방지)
        $lines = @(Get-Content -Path $logFile -ErrorAction SilentlyContinue)
        if ($lines.Count -gt 2000) { $lines[-1000..-1] | Set-Content -Path $logFile }
    } catch {}
}

function Get-LoopState { (Get-ScheduledTask -TaskName "Archive-CollectLoop" -ErrorAction SilentlyContinue).State }

$state = Get-LoopState
if (-not $state) { Write-WdLog "ERROR: Archive-CollectLoop task not found"; exit 1 }
if ($state -eq "Running") { Write-WdLog "ok (Running)"; exit 0 }

# 죽은 것처럼 보임 → 재기동 중/일시 상태 오판 방지로 잠깐 뒤 재확인
Start-Sleep -Seconds 5
$state = Get-LoopState
if ($state -eq "Running") { Write-WdLog "recovered on its own -> skip"; exit 0 }

# 확정적으로 죽음. 이 루프의 잔여 python만 정리(명령줄 매칭). CommandLine 조회 불가(권한) 프로세스는 제외.
$loopProcs = @(
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and ($_.CommandLine -match 'run_daily_archive_loop|index_tail_realtime|batch_recollect') }
)
foreach ($p in $loopProcs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
if ($loopProcs.Count -gt 0) {
    Start-Sleep -Seconds 2
    # 루프 잔여가 있었으면 그 브라우저(헤드리스 크롬)도 정리 — 프로필 잠금 해제
    Get-Process chrome-headless-shell -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

# 재기동 직전 최종 재확인(그새 살아났으면 중복 기동 방지)
if ((Get-LoopState) -eq "Running") { Write-WdLog "started during cleanup -> skip restart"; exit 0 }
try {
    Start-ScheduledTask -TaskName "Archive-CollectLoop"
    Write-WdLog "was '$state' -> cleaned $($loopProcs.Count) loop python + restarted"
} catch {
    Write-WdLog "restart FAILED: $($_.Exception.Message)"
    exit 1
}
