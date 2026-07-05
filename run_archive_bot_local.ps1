$ErrorActionPreference = "Stop"

cd "C:\projects\naver_cafe_archive"

# 2026-06-30: 네이버가 /f-e/ 멤버 목록을 빈 SPA 셸로 변경해 목록 파싱이 0행이 됨.
# 실제 글 목록은 /ca-fe/ 주소에 있고 기존 파서로 정상 파싱됨 → /ca-fe/로 교체.
$ListUrl = "https://cafe.naver.com/ca-fe/cafes/29082876/members/THEA7uBzD6uKXKno57_Bl7jItzRnvmuDMltnPsGI9BY"

Write-Host ""
Write-Host "========================================"
Write-Host " Archive Bot 시작"
Write-Host " 브라우저가 열리면 네이버 로그인 후"
Write-Host " PowerShell 창에서 엔터를 누르세요."
Write-Host " 종료는 Ctrl + C"
Write-Host "========================================"
Write-Host ""

& ".\.venv\Scripts\python.exe" "scripts\run_daily_archive_loop.py" --interactive-login --market-schedule --list-url $ListUrl --realtime-index --stop-after-empty-pages 5

Write-Host ""
Write-Host "Archive Bot 종료됨. 창을 닫으려면 엔터."
Read-Host
