# scripts/start_archive_loop_boot.ps1
# 미니PC 부팅(로그온) 시 자동 기동되는 아카이브 수집 상주 루프 런처 (무인 전용).
#
# start_archive_loop.ps1(대화형·수동 기동)과의 차이:
#   - --interactive-login 없음: 무인에서 로그인 만료 시 콘솔 Enter 대기로 멈추지 않게 한다.
#       (만료되면 사이클이 깔끔히 종료 → Task Scheduler 실패 재시작이 복구를 시도하고,
#        RAG liveness 신호가 '마지막 수집일 정체'로 정체를 노출한다. 재로그인은 형이 헤디드로 수동.)
#   - --duration-hours 큰 값: 24h 후 자동 종료되지 않고 영구 상주. 재부팅이 자연 리프레시.
#   - 고아 lock 선제거: 재부팅 직후 이전 인스턴스의 lock이 아직 30분 stale이 안 됐어도
#       즉시 재기동되게 한다(부팅 시점엔 살아있는 인스턴스가 없다).
#   - $ListUrl 실제 값 내장: 무인 기동이라 플레이스홀더로 거부하면 안 된다.

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

# cp949 인코딩으로 봇이 조용히 죽는 것 방지 (한글 출력)
$env:PYTHONUTF8 = "1"

# 헤드리스 여부: 기본은 config 기본값(headed, 창 뜸)을 따른다. 5-A/5-B가 headed로 검증됨.
# 헤드리스(창 없이) 무인 운영을 원하고 헤드리스 프로브가 (True, N rows)로 확인됐다면
# 아래 주석을 해제한다. (로그인 재시드는 별도로 headed 필요)
# $env:HEADLESS = "true"

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "[archive-boot] Python virtualenv not found: $Python" -ForegroundColor Red
    exit 1
}

# 멘토 작성글 목록 URL (이미 repo에 공개된 값 — src/batch_recollect.py CAFE_MEMBERS_URL과 동일)
$ListUrl = "https://cafe.naver.com/ca-fe/cafes/29082876/members/THEA7uBzD6uKXKno57_Bl7jItzRnvmuDMltnPsGI9BY"

# 부팅/재시작 시 이전 인스턴스의 고아 lock 제거 (30분 stale 대기 없이 즉시 재기동).
Remove-Item (Join-Path $ProjectRoot "state\archive_loop.lock") -Force -ErrorAction SilentlyContinue

Write-Host "[archive-boot] 무인 상주 수집 루프 시작 (market-schedule, realtime, headless=$($env:HEADLESS))"

# --market-schedule : 시간대별 타임테이블(08-16시 5분 … 23-06시 중단)
# --realtime-index  : 인프로세스 경로(세션 재사용·블록 안전). 무인 필수.
# --duration-hours  : 20년(≈영구). 재부팅이 자연 리프레시.
& $Python "scripts\run_daily_archive_loop.py" `
    --market-schedule `
    --realtime-index `
    --duration-hours 175200 `
    --list-url $ListUrl

exit $LASTEXITCODE
