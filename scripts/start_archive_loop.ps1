$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "[archive] Python virtualenv not found: $Python" -ForegroundColor Red
    Write-Host "[archive] Create or restore .venv before running the archive loop."
    exit 1
}

# Replace this placeholder with the mentor teacher article-list URL before running.
$ListUrl = "<멘토선생님 작성글 목록 URL>"

if ([string]::IsNullOrWhiteSpace($ListUrl) -or $ListUrl.Contains("<") -or $ListUrl.Contains(">") -or $ListUrl -like "*URL*") {
    Write-Host "[archive] Refusing to start: edit scripts\start_archive_loop.ps1 and set `$ListUrl first." -ForegroundColor Yellow
    Write-Host "[archive] Use the mentor teacher article-list URL confirmed in the browser."
    exit 2
}

Write-Host "[archive] Market-schedule archive loop"
Write-Host "[archive] If a Naver login window appears, log in manually in the browser."
Write-Host "[archive] When the mentor teacher article list is visible, return here and press Enter if prompted."
Write-Host "[archive] Market schedule controls when the proven archive routine runs."
Write-Host "[archive] No automatic login or CAPTCHA bypass is performed."

# --realtime-index: 수집·본문을 인프로세스(브라우저 세션 재사용)로 돌린다. 이 경로만이
# 무인 안전하다 — 세션 만료 시 콘솔 Enter 대기로 멈추지 않고 서킷브레이커로 중단하고,
# 차단(login_required)을 조용한 0건 성공으로 위장하지 않는다. (subprocess 경로는 무인 부적합)
& $Python "scripts\run_daily_archive_loop.py" `
    --interactive-login `
    --market-schedule `
    --realtime-index `
    --list-url $ListUrl

exit $LASTEXITCODE
