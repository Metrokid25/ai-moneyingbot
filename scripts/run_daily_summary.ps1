$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot
$env:PYTHONUTF8 = "1"

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "[daily_summary] venv 없음: $Python" -ForegroundColor Red
    exit 1
}

# 텔레그램 토큰은 .env(RAG_TELEGRAM_BOT_TOKEN/CHAT_ID)에서 notify_telegram이 자동 로드.
& $Python "scripts\daily_collection_summary.py"
exit $LASTEXITCODE
