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
`--bootstrap-existing`은 과거 검증용이며 shadow에서만 허용된다.

## 장애 복구

- Archive DB 잠금/일시 읽기 실패: 체크포인트는 성공한 주기 끝에서만 이동한다.
  상주 모드는 다음 주기에 재시도한다.
- Trading API 일시 실패: Reader 행은 `delivery_failed`로 남고 30초부터 최대 1시간의
  exponential backoff로, 주기당 최대 10건만 재시도한다. 신규 Archive 스캔을 먼저
  수행하므로 오래된 장애 backlog가 새 글 판독을 막지 않는다.
- 설정 누락과 영구 4xx는 `delivery_rejected`로 종료해 무한 재시도하지 않는다.
- Archive의 `posted_at`이 레거시 `YYYY.MM.DD. HH:MM`/naive 형식이어도 Reader가
  Asia/Seoul 오프셋이 있는 ISO-8601로 변환한 뒤 API에 전달한다.
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

2026-08-07 로컬 검증 기준: 최신 main 통합 후 Reader 저장소 전체 `823 passed`, Trading 저장소 전체
`486 passed, 1 skipped`, Fixture E2E에서 `SK하이닉스(000660)` 등록 → `trading.db` 감사행 →
일반 관심종목 조회 즉시 노출 → Paper Runner 당일 제외·익일 편입까지 통과했다.
운영 미니PC 배포/프로세스 재기동은 별도 운영 단계이며 배포 전에는 shadow를 유지한다.
