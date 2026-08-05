# Mentor Signal Reader Operations

## 설정

`.env.example`을 기준으로 비밀값은 미추적 `.env`에만 둔다.

```text
MENTOR_SIGNAL_MODE=shadow
MENTOR_AUTHOR_ID=굿머닝
MENTOR_ARCHIVE_DB=C:\projects\naver_cafe_archive\data\archive.db
MENTOR_SIGNAL_STATE_DB=C:\projects\naver_cafe_archive\state\mentor_signals.db
MENTOR_STOCK_MASTER_PATH=C:\bot-shared\mentor-stock-master.json
MENTOR_STOCK_ALIASES_PATH=
MENTOR_SIGNAL_CONFIDENCE_THRESHOLD=0.95
MENTOR_SIGNAL_POLL_SECONDS=60
TRADING_BOT_BASE_URL=http://127.0.0.1:8000
TRADING_BOT_WEB_KEY=<WEB_SHARED_KEY와 동일>
```

Telegram은 기존 `RAG_TELEGRAM_BOT_TOKEN`과 `RAG_TELEGRAM_CHAT_ID`를 재사용한다.

## 종목 마스터 내보내기

Trading Bot 소유 프로세스가 명시적 참조 스냅샷을 생성한다. Reader가
`trading.db` 또는 Trading Bot 내부 캐시를 직접 열게 하지 않는다.

```powershell
cd C:\trading-bot
.\.venv\Scripts\python.exe scripts\export_mentor_stock_master.py `
  --output C:\bot-shared\mentor-stock-master.json
```

## 실행

안전한 최초 구동은 두 번 수행한다. 첫 번째는 기준점만 만들고, 두 번째부터 새 글을
처리한다.

```powershell
cd C:\projects\naver_cafe_archive
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe scripts\run_mentor_signal_reader.py --mode shadow --once
.\.venv\Scripts\python.exe scripts\run_mentor_signal_reader.py --mode shadow --loop
```

Shadow 관찰과 작성자/마스터 확인 후에만 `--mode paper`로 바꾼다. `live`는 항상
`Live mentor signal trading is disabled by policy.`로 종료한다.

## 장애 복구

- Archive DB 잠금/일시 읽기 실패: 체크포인트는 성공한 주기 끝에서만 이동한다.
  상주 모드는 다음 주기에 재시도한다.
- Trading API 실패: Reader 행은 `delivery_failed`로 남고 다음 주기 시작 때 재시도한다.
- 재시작: `reader_meta`의 `last_article_id`/`last_scan_at`에서 이어간다.
- 상태 DB 손상: 프로세스를 중지하고 파일을 백업한 뒤 새 DB로 시작한다. 새 DB 첫
  실행은 현시점 기준점만 잡으므로 과거 전체가 재전송되지 않는다.
- 롤백: Reader 프로세스를 중지하고 Trading 웹앱을 이전 커밋으로 되돌린다. 이미
  추가된 관심종목은 기존 웹 UI에서 수동 제거하며 주문/포지션 자동 청산은 하지 않는다.

## 미니PC 배포

작업 브랜치를 pull한 후 양 저장소 테스트를 실행하고, Trading 웹앱 재기동은 기존
운영 규칙대로 장 마감 후 WMI로만 한다. Reader는 먼저 shadow로 별도 상주 등록하고
최소 관찰 기간 동안 판독/오탐/지연을 확인한다. 이 작업은 미니PC에 자동 배포하거나
운영 프로세스를 재기동하지 않는다.

로컬 Fixture E2E 검증:

```powershell
.\.venv\Scripts\python.exe scripts\verify_mentor_signal_e2e.py `
  --trading-repo C:\trading-bot `
  --trading-python C:\trading-bot\.venv\Scripts\python.exe
```
