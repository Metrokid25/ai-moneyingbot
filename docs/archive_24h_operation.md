# Archive Bot 24h Operation

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

## Windows 작업 스케줄러 초안

작업 스케줄러 또는 시작 프로그램의 목적은 PC 재부팅 후 Archive Bot 루프를 다시 실행하기 쉽게 만드는 것이다.
이번 단계에서는 저장소 안에 자동 실행 ps1을 만들지 않고, 등록 절차만 문서화한다.

등록 전 안전 확인:

```powershell
cd C:\projects\naver_cafe_archive
.\.venv\Scripts\Activate.ps1
python scripts\run_daily_archive_loop.py --help
python scripts\run_daily_archive_loop.py --status
```

작업 스케줄러 작업의 동작 예시:

- 프로그램: `powershell.exe`
- 시작 위치: `C:\projects\naver_cafe_archive`
- 인수 예시:

```powershell
-NoProfile -ExecutionPolicy Bypass -Command "cd C:\projects\naver_cafe_archive; .\.venv\Scripts\Activate.ps1; python scripts\run_daily_archive_loop.py --list-url '멘토선생님_작성글_목록_URL'"
```

주의 사항:

- `list-url`에는 사용자가 직접 멘토선생님 작성글 목록 URL을 넣어야 한다.
- 실제 등록 전 `--help`, `--status`를 먼저 확인한다.
- 중복 실행을 피해야 한다. 이미 루프가 실행 중이면 새 작업을 시작하지 않는다.
- 네이버 로그인은 사용자가 직접 유지한다.

## 중복 실행 방지 TODO

현재 루프에는 강제 중복 실행 방지가 없다.
이번 작업에서는 무리하게 구현하지 않고 다음 작업자가 바로 구현할 수 있도록 설계 후보를 남긴다.

권장 구현 방향:

1. `state/archive_loop_status.json`의 `is_running`과 `updated_at`을 읽는다.
2. `is_running=true`이고 `updated_at`이 최근이면 새 루프 시작을 거부한다.
3. stale 기준은 `max(interval_seconds * 2, 1800초)`처럼 설정한다.
4. stale이면 경고를 출력하고 새 루프 시작을 허용하되 `stop_reason` 또는 별도 필드에 stale takeover를 남긴다.
5. status 파일에 `pid`를 추가 기록한다.
6. Windows에서는 `Get-Process -Id <pid>`로 이전 프로세스 존재를 확인한다.
7. 더 엄격한 방식이 필요하면 `state/archive_loop.lock` 파일을 만들고 원자적 생성 방식으로 lock 획득을 구현한다.
8. 루프 정상 종료 시 lock 파일을 제거하고, 비정상 종료 시 stale 기준과 pid 확인으로 복구한다.

테스트 후보:

- status 파일이 없으면 정상 시작
- `is_running=true`, `updated_at`이 fresh이면 시작 거부
- `is_running=true`, `updated_at`이 stale이고 pid가 없으면 takeover 허용
- `is_running=true`, pid 프로세스가 살아 있으면 시작 거부
- 정상 종료 시 lock 파일 제거
