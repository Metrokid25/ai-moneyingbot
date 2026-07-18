# Archive 수집 봇 워치독 — 1시간마다 실행.
# Archive-CollectLoop가 'Running'이 아니면(0xC000013A 세션 kill 등으로 죽었으면)
# 잔여 브라우저(헤드리스 크롬)만 정리하고 재기동한다. 정상이면 아무것도 안 함.
# 주의: python 프로세스는 광범위 kill하지 않는다(RAG 색인/일일요약 오탐 방지).
#       chrome-headless-shell은 수집 루프만 쓰므로 정리해 프로필 잠금 충돌을 푼다.
$ErrorActionPreference = "Continue"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$logDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$log = Join-Path $logDir "watchdog.log"
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

$task = Get-ScheduledTask -TaskName "Archive-CollectLoop" -ErrorAction SilentlyContinue
if (-not $task) {
    Add-Content -Path $log -Value "$ts [watchdog] ERROR: Archive-CollectLoop task not found"
    exit 1
}

if ($task.State -ne "Running") {
    Get-Process chrome-headless-shell -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    try {
        Start-ScheduledTask -TaskName "Archive-CollectLoop"
        Add-Content -Path $log -Value "$ts [watchdog] CollectLoop was '$($task.State)' -> cleaned stray chrome + restarted"
    } catch {
        Add-Content -Path $log -Value "$ts [watchdog] restart FAILED: $($_.Exception.Message)"
    }
} else {
    Add-Content -Path $log -Value "$ts [watchdog] ok (Running)"
}
