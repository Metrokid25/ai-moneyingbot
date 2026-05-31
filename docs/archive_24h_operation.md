# Archive Bot 24h Operation

## Manual Login With Cafe URL

Manual login must be done by the user in the Archive Bot browser profile before real collection.
Use the mentor teacher article-list URL, not only the Naver home/login page:

```powershell
.\.venv\Scripts\python.exe scripts\daily_archive.py --login --login-url "<멘토선생님 작성글 목록 URL>"
```

- Naver home login alone may not be enough to confirm Cafe article-list access.
- `browser profile exists` only means the folder exists; it does not prove that Naver Cafe login is valid.
- The manual login browser is opened in headed mode so the user can complete login and verification directly.
- After Enter, `--login --login-url` reopens the same URL in the same persistent profile and checks whether it is still `login_required`.
- If verification fails, keep the browser open, make sure the article list is actually visible, and press Enter again.
- Proceed to a real `run_daily_archive_loop.py` collection test only after login verification succeeds.
- In the bot-only browser, open the mentor teacher article-list URL and confirm that the article list is visible.
- The command does not collect articles and does not write to the DB, state, or reports.
- If captcha or identity verification appears, the user must handle it manually.
- After confirming access, press Enter in PowerShell to close the login preparation command.
- Do not put the manual login command in Windows Task Scheduler.

Login-required recovery:

1. Check `stop_reason` with `.\.venv\Scripts\python.exe scripts\run_daily_archive_loop.py --status`.
2. Confirm the archive loop has stopped.
3. Run `.\.venv\Scripts\python.exe scripts\daily_archive.py --login --login-url "<멘토선생님 작성글 목록 URL>"` manually.
4. In the opened browser, complete login, CAPTCHA, or identity verification yourself.
5. Confirm the mentor teacher article list is visible, then press Enter in PowerShell.
6. Restart the loop with `.\.venv\Scripts\python.exe scripts\run_daily_archive_loop.py --list-url "<멘토선생님 작성글 목록 URL>"`.

Scheduler templates must run only `run_daily_archive_loop.py`; they must not include the manual login command or `--login-url`.

Korean operator note:

- 네이버 홈 로그인만으로는 부족할 수 있다.
- 봇 전용 브라우저에서 멘토선생님 작성글 목록 URL까지 열어보고 글 목록이 보이는지 확인해야 한다.
- 확인 후 PowerShell에서 Enter로 종료한다.
- 이 명령은 작업 스케줄러에 넣지 않는다.

이 문서는 Archive Bot의 장시간 운영, 상태 점검, 복구 절차를 정리한다.
실제 수집을 시작하기 전에는 멘토선생님 작성글 목록 URL만 넣으면 된다.

## 기본 실행

프로젝트 폴더에서 가상환경을 활성화한 뒤 24시간 루프를 실행한다.

```powershell
cd C:\projects\naver_cafe_archive
.\.venv\Scripts\Activate.ps1
python scripts\run_daily_archive_loop.py --list-url "멘토선생님_작성글_목록_URL"
```

기본값은 24시간, 600초 간격, 회당 10개, 최대 144회다.

필요하면 명시적으로 조정한다.

```powershell
python scripts\run_daily_archive_loop.py --list-url "멘토선생님_작성글_목록_URL" --duration-hours 24 --interval-seconds 600 --limit 10
```

`daily_archive.py --execute`를 직접 실행하기보다 `run_daily_archive_loop.py`를 우선 사용한다.
루프 스크립트가 heartbeat/status, 로그, block signal 중단, 반복 실행 범위를 함께 관리한다.

## 상태 확인

실제 수집을 실행하지 않고 현재 상태만 확인한다.

```powershell
python scripts\run_daily_archive_loop.py --status
```

상태 파일이 없으면 `no status file` 메시지가 출력된다.
상태 파일이 있으면 운영자가 바로 읽을 수 있는 요약이 출력된다.

주요 항목:

- `running`: 루프가 마지막 상태 기준 실행 중인지 여부
- `started_at`: 루프 시작 시각
- `updated_at`: status 파일이 마지막으로 갱신된 시각
- `current_run / max_runs`: 현재 완료 또는 진행 중인 회차와 최대 회차
- `interval_seconds`: 실행 간격
- `duration_hours`: 총 실행 시간
- `limit`: 회당 수집 제한
- `list_url_preview`: URL 일부만 표시한 값
- `last_run_started_at`: 최근 회차 시작 시각
- `last_run_finished_at`: 최근 회차 종료 시각
- `last_return_code`: 최근 `daily_archive.py` 반환 코드
- `last_saved`: 최근 저장 수
- `last_duplicates`: 최근 중복 수
- `last_failed`: 최근 실패 수
- `last_report_path`: 최근 리포트 경로
- `stop_reason`: 루프 중단 사유

## Preflight 점검

실제 수집을 시작하기 전에는 preflight를 먼저 실행한다.
preflight는 실제 수집, 브라우저 실행, 네트워크 접근, `daily_archive.py --execute` 호출을 하지 않는다.

```powershell
python scripts\run_daily_archive_loop.py --preflight
```

출력 의미:

- `[OK]`: 실운영 전 기본 조건이 충족됨
- `[WARN]`: 확인이 필요하지만 자동으로 실제 수집을 막지는 않음
- `[FAIL]`: 실제 수집을 시작하면 안 되는 상태

`[FAIL]`이 하나라도 있으면 exit code `2`로 종료된다.
`[WARN]`만 있으면 내용을 확인한 뒤 진행할 수 있다.
모든 항목이 `[OK]`이면 exit code `0`이다.

preflight는 `data/archive.db`를 읽기 전용으로 열고 `articles` count만 확인한다.
DB 파일을 수정하지 않는다.
`articles` count가 `0`이면 `[FAIL]`로 보고 실제 수집을 시작하지 않는다.

preflight에서 `list-url`은 필요하지 않다.
실제 수집 실행 시에는 멘토선생님 작성글 목록 URL이 필요하다.

## 네이버 로그인 세션 준비

Archive Bot은 Playwright persistent browser profile을 사용한다.
일반 Chrome 또는 Edge에서 네이버에 로그인한 상태와 Archive Bot이 사용하는 Playwright profile의 로그인 상태는 다를 수 있다.
실제 수집 전에 아래 수동 로그인 명령으로 Archive Bot 전용 profile에 로그인 세션을 저장한다.

```powershell
.\.venv\Scripts\python.exe scripts\daily_archive.py --login --login-url "<멘토선생님 작성글 목록 URL>"
```

기본 profile 경로는 `state/browser_profile`이다.
다른 경로를 쓰려면 동일한 경로를 로그인 준비와 수집 실행에 함께 지정한다.

```powershell
.\.venv\Scripts\python.exe scripts\daily_archive.py --login --login-url "<멘토선생님 작성글 목록 URL>" --browser-profile-dir state\browser_profile
```

명령을 실행하면 브라우저가 열리고 사용자가 직접 네이버 로그인을 완료해야 한다.
아이디/비밀번호 자동 입력, CAPTCHA 우회, 본인인증 우회는 하지 않는다.
CAPTCHA 또는 본인인증이 뜨면 사용자가 직접 처리한다.
로그인 완료 후 콘솔에서 Enter를 누르면 로그인 준비 명령이 종료된다.

이후 `daily_archive.py --execute`와 `run_daily_archive_loop.py`는 기본적으로 같은 `state/browser_profile`을 재사용한다.
첫 수집이나 장시간 루프에서 `login_required`가 다시 발생하면 다음 순서로 처리한다.

1. 실행 중인 루프가 종료됐는지 `python scripts\run_daily_archive_loop.py --status`로 확인한다.
2. `.\.venv\Scripts\python.exe scripts\daily_archive.py --login --login-url "<멘토선생님 작성글 목록 URL>"`을 실행한다.
3. 열린 브라우저에서 네이버 로그인, CAPTCHA, 본인인증을 직접 완료하고 멘토선생님 작성글 목록이 보이는지 확인한다.
4. 콘솔에서 Enter를 눌러 종료한다.
5. `python scripts\run_daily_archive_loop.py --preflight`로 profile 상태를 확인한다.
6. 사용자 승인 후 수집 루프를 다시 시작한다.

`state/browser_profile`은 런타임 브라우저 프로필이며 커밋 대상이 아니다.
`state/`는 `.gitignore`에 포함되어 있으므로 profile 파일을 git에 추가하지 않는다.

## 파일 위치

- 루프 상태: `state/archive_loop_status.json`
- 루프 로그: `logs/archive_loop/`
- 일일 리포트: `reports/`

`state/archive_loop_status.json`은 운영 상태를 기계가 읽을 수 있게 저장하는 heartbeat 파일이다.
직접 수정하지 말고 `--status` 명령으로 확인한다.

## 재부팅 후 재시작

1. 네이버 로그인이 유지되어 있는지 브라우저에서 직접 확인한다.
2. PowerShell을 열고 프로젝트 폴더로 이동한다.
3. `.venv`를 활성화한다.
4. `python scripts\run_daily_archive_loop.py --status`로 이전 종료 상태와 `stop_reason`을 확인한다.
5. 기존 루프 프로세스가 남아 있지 않은지 확인한다.
6. 멘토선생님 작성글 목록 URL을 넣어 루프를 다시 시작한다.

```powershell
cd C:\projects\naver_cafe_archive
.\.venv\Scripts\Activate.ps1
python scripts\run_daily_archive_loop.py --status
python scripts\run_daily_archive_loop.py --list-url "멘토선생님_작성글_목록_URL"
```

사용자가 네이버 로그인 세션은 직접 유지해야 한다.
로그인 만료, CAPTCHA, 권한 문제는 자동으로 해결하지 않는다.

## Block/Login/CAPTCHA/권한 문제 확인 순서

루프가 `stop_reason`에 block, login, captcha, permission 관련 메시지를 남기고 멈추면 다음 순서로 확인한다.

1. `python scripts\run_daily_archive_loop.py --status`로 `stop_reason`, `last_return_code`, `last_failed`, `last_report_path`를 확인한다.
2. `logs/archive_loop/`의 당일 로그에서 최근 회차의 stdout/stderr 요약을 확인한다.
3. `reports/`의 최근 리포트가 있으면 실패 항목과 notes를 확인한다.
4. 브라우저에서 네이버 카페 접속, 로그인 유지, CAPTCHA 표시 여부, 멘토선생님 작성글 목록 접근 권한을 직접 확인한다.
5. 문제가 해결된 뒤 기존 루프가 종료되어 있는지 확인하고 다시 시작한다.

## Windows 작업 스케줄러 운영 준비

작업 스케줄러 등록 목적은 PC 재부팅 후 Archive Bot 24시간 루프를 자동으로 다시 시작할 수 있게 만드는 것이다.
권장 방식은 사용자가 Windows에 로그온한 상태에서 실행하는 것이다.
네이버 로그인 세션은 자동으로 만들거나 갱신하지 않으므로 사용자가 브라우저에서 직접 유지해야 한다.

### A. 수동 로그인 사전 준비

작업 스케줄러를 등록하기 전에 사용자가 직접 한 번 실행한다.
이 단계는 브라우저를 열고 사용자의 Enter 입력을 기다리는 수동 절차이므로 작업 스케줄러에 넣지 않는다.

```powershell
cd C:\projects\naver_cafe_archive
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe scripts\daily_archive.py --login --login-url "<멘토선생님 작성글 목록 URL>"
```

열린 브라우저에서 사용자가 직접 네이버 로그인, CAPTCHA, 본인인증을 완료한다.
로그인 완료 후 콘솔에서 Enter를 눌러 종료한다.
이렇게 저장된 `state/browser_profile`을 이후 자동 실행 루프가 재사용한다.

### B. 작업 스케줄러 자동 실행

작업 스케줄러에는 `run_daily_archive_loop.py` 실행만 넣는다.
작업 스케줄러는 브라우저 수동 로그인 대기 명령을 실행하지 않는다.

실제 등록 전에는 프로젝트 폴더에서 안전 확인 명령을 먼저 실행한다.
이 명령들은 실제 수집을 시작하지 않는다.

```powershell
cd C:\projects\naver_cafe_archive
.\.venv\Scripts\Activate.ps1
python scripts\run_daily_archive_loop.py --help
python scripts\run_daily_archive_loop.py --status
python scripts\run_daily_archive_loop.py --preflight
```

실제 실행 명령 템플릿은 다음과 같다.
멘토선생님 작성글 목록 URL만 넣으면 된다.

```powershell
.\.venv\Scripts\python.exe scripts\run_daily_archive_loop.py --list-url "<멘토선생님 작성글 목록 URL>"
```

placeholder URL 상태로는 실제 실행하지 않는다.
중복 실행은 `state/archive_loop.lock`으로 차단된다.
상태는 `python scripts\run_daily_archive_loop.py --status`로 확인하고, 내부 상태 파일은 `state/archive_loop_status.json`에 저장된다.
루프 로그는 `logs/archive_loop/`에서 확인한다.

문제가 생겼을 때는 다음 순서로 확인한다.

1. `python scripts\run_daily_archive_loop.py --status`
2. `reports/`의 최신 report
3. `logs/archive_loop/`의 최신 loop log
4. 브라우저의 네이버 로그인 상태
5. block, captcha, 권한 관련 문구

`login_required`가 발생하면 루프는 `--status`의 `stop_reason`에 멈춤 사유를 표시한다.
사용자가 직접 `.\.venv\Scripts\python.exe scripts\daily_archive.py --login --login-url "<멘토선생님 작성글 목록 URL>"`을 실행해 로그인 세션을 다시 준비한다. 브라우저에서 글 목록이 보이는지 확인한 뒤 Enter로 종료하고 루프를 재시작한다.

## PowerShell 래퍼 예시

저장소 안에 자동 실행 ps1을 직접 만들지는 않는다.
아래 예시는 사용자가 별도 위치에 직접 만들 수 있는 래퍼 초안이다.
`$ListUrl`이 placeholder인 상태에서는 실제 실행하지 않는다.
이 래퍼는 무인 자동 실행용이므로 manual login command를 포함하지 않는다.

```powershell
$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\projects\naver_cafe_archive"
$ListUrl = "<멘토선생님 작성글 목록 URL>"
$RunLogDir = Join-Path $ProjectRoot "logs\archive_loop"
$RunLog = Join-Path $RunLogDir ("scheduler-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

if ($ListUrl -like "<*>" -or $ListUrl -like "*URL*") {
    throw "List URL placeholder is still set. Do not start real collection."
}

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $RunLogDir | Out-Null

.\.venv\Scripts\Activate.ps1

python scripts\run_daily_archive_loop.py --help
python scripts\run_daily_archive_loop.py --status
python scripts\run_daily_archive_loop.py --preflight

.\.venv\Scripts\python.exe scripts\run_daily_archive_loop.py --list-url $ListUrl *> $RunLog
```

운영 중 stdout/stderr는 `$RunLog`에 남는다.
루프 자체 로그는 별도로 `logs/archive_loop/`에 남는다.
중복 실행은 lock guard가 막지만, 작업 스케줄러에서도 "이미 실행 중이면 새 인스턴스 시작 안 함" 설정을 권장한다.

## 작업 스케줄러 설정값

작업 스케줄러에서 새 작업을 만들 때 다음 값을 기준으로 등록한다.

- 트리거: 사용자가 로그온할 때 또는 PC 시작 시
- 동작: `powershell.exe` 실행
- 인수 예시: `-ExecutionPolicy Bypass -File "사용자가 만든 래퍼 ps1 경로"`
- 시작 위치: `C:\projects\naver_cafe_archive`
- 조건: AC 전원에서만 시작할지 여부는 사용자 선택
- 설정: 이미 실행 중이면 새 인스턴스 시작 안 함
- 설정: 실패 시 재시작
- 설정: 가능한 경우 예약된 시작 시간을 놓치면 즉시 실행

주의 사항:

- 실제 등록 전 래퍼를 1회 수동 실행해 `--help`, `--status` 확인이 정상인지 확인한다.
- 실제 수집 실행은 사용자가 명시 승인한 뒤에만 한다.
- `list-url`에는 사용자가 직접 멘토선생님 작성글 목록 URL을 넣는다.
- 중복 실행을 피해야 한다. lock guard가 막더라도 작업 스케줄러 설정에서 새 인스턴스를 시작하지 않게 둔다.
- 수동 로그인 준비는 작업 스케줄러가 아니라 사용자가 직접 실행한다.
- 네이버 로그인은 사용자가 직접 유지한다.

## 중복 실행 방지

`run_daily_archive_loop.py`는 실제 루프를 시작하기 전에 `state/archive_loop.lock` 파일로 중복 실행을 막는다.
이미 실행 중인 루프가 있으면 새 루프는 시작하지 않고 non-zero exit code로 종료된다.
이 동작은 같은 PC에서 24시간 루프가 두 개 이상 동시에 실행되어 같은 목록을 중복 처리하는 상황을 막기 위한 것이다.

lock 파일에는 다음 정보가 JSON으로 기록된다.

- `pid`: lock을 가진 프로세스 ID
- `started_at`: lock 획득 시각
- `updated_at`: 최근 heartbeat 시각
- `command`: 실행 인자 요약
- `lock_version`: lock 파일 형식 버전

루프는 status 파일을 갱신할 때 lock의 `updated_at`도 함께 갱신한다.
정상 종료, block signal 중단, non-zero return code, duration 도달, max-runs 도달, KeyboardInterrupt 종료에서는 가능한 lock 파일을 제거한다.

stale lock은 `updated_at`이 stale 기준보다 오래된 lock이다.
기본 stale 기준은 30분이며, 필요하면 `--lock-stale-minutes`로 조정할 수 있다.
PC 강제 종료나 전원 차단처럼 이전 프로세스가 lock을 지우지 못한 경우에도 stale 기준이 지나면 새 실행이 자동으로 lock을 인수한다.
JSON이 깨졌거나 필수 필드가 없는 lock도 corrupt/stale lock으로 보고 인수할 수 있다.

수동으로 `state/archive_loop.lock`을 삭제하는 것은 최후 수단이다.
먼저 `python scripts\run_daily_archive_loop.py --status`와 Windows 작업 관리자 또는 PowerShell의 `Get-Process`로 실제 루프가 살아 있는지 확인한다.
실행 중인 루프가 확실히 없고 stale 기준을 기다릴 수 없는 경우에만 lock 파일 삭제를 고려한다.

## 24시간 실운영 전 체크리스트

- `git status -sb` 확인
- `pytest --basetemp=.tmp\pytest` 통과 확인
- `archive.db` 백업 존재 확인
- 네이버 로그인 유지 확인
- `.\.venv\Scripts\python.exe scripts\daily_archive.py --login --login-url "<멘토선생님 작성글 목록 URL>"`으로 Archive Bot profile 로그인 및 카페 글 목록 접근 확인
- 멘토선생님 작성글 목록 URL 준비
- `python scripts\run_daily_archive_loop.py --preflight` 확인
- `python scripts\run_daily_archive_loop.py --status` 확인
- 기존 `state/archive_loop.lock`과 `state/archive_loop_status.json` 상태 확인
- 작업 스케줄러 중복 실행 설정 확인
- 사용자가 명시 승인한 뒤에만 실제 수집 실행
