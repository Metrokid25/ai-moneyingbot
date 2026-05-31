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
Write-Host "[archive] Login preparation runs before market-schedule waiting; collection still waits for active hours."
Write-Host "[archive] No automatic login or CAPTCHA bypass is performed."

& $Python "scripts\run_daily_archive_loop.py" `
    --interactive-login `
    --market-schedule `
    --list-url $ListUrl

exit $LASTEXITCODE
