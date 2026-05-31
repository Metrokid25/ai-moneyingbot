$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "[archive] Python virtualenv not found: $Python" -ForegroundColor Red
    Write-Host "[archive] Create or restore .venv before running the one-shot archive command."
    exit 1
}

# Replace this placeholder with the mentor teacher article-list URL before running.
$ListUrl = "<멘토선생님 작성글 목록 URL>"

if ([string]::IsNullOrWhiteSpace($ListUrl) -or $ListUrl.Contains("<") -or $ListUrl.Contains(">") -or $ListUrl -like "*URL*") {
    Write-Host "[archive] Refusing to start: edit scripts\run_archive_once.ps1 and set `$ListUrl first." -ForegroundColor Yellow
    Write-Host "[archive] Use the mentor teacher article-list URL confirmed in the browser."
    exit 2
}

& $Python "scripts\run_daily_archive_loop.py" `
    --interactive-login `
    --list-url $ListUrl `
    --max-runs 1

exit $LASTEXITCODE
