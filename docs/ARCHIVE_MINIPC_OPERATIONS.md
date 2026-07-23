# Archive봇 미니PC 무인 운영 러너북 (ARCHIVE_MINIPC_OPERATIONS)

> **이 문서가 Archive봇 배포·운영의 기준 문서다** (DEPLOY_MINIPC.md가 "Archive 봇 배포 문서를 따르라"고
> 가리키는 그 문서). 대상: 미니PC(24/7 운영+개발 겸용, Windows 11) `C:\projects\naver_cafe_archive`.
> 작성 2026-07-18 · 기준 커밋 `7d01def`.
> **작업 전 필독**: 요약·문서(이 문서 포함)를 믿지 말고 코드로 재확인하라. 시작하면 `git fetch origin` 먼저.
> **현재 미니PC 작업 시작점**: `docs/ARCHIVE_MINIPC_HANDOFF.md`를 먼저 실행한 뒤 이 러너북을 참조한다.

---

## 1. 시스템 한 장 요약

```
[수집: Archive봇 — 이 문서]                         [색인: RAG봇 — DEPLOY_MINIPC.md]
네이버 카페(29082876) 멘토 글                        archive.db 읽기전용
  → REST API 수집 (member_api.py)                    → 신규 청크 임베딩 → Qdrant
  → data/archive.db (16GB, 43.6k+건, 쓰기는 Archive만)  → 텔레그램 색인통지 (매일 16:30)
  → 상주 루프 (market schedule, 헤드리스)
```

- **3봇 소유권 계약은 `docs/OWNERSHIP.md`가 최상위** — archive.db/mentor.db 쓰기는 Archive봇만,
  Qdrant는 RAG봇만, trading-bot 데이터 접근 금지, 교차키 `article_id`,
  **articles 스키마(`posted_at`/`saved_at`/`status`) 동결**(RAG 생존신호가 의존).
- **RAG 소유 파일 수정 금지**(재사용 import는 OK): `scripts/notify_telegram.py`,
  `scripts/run_rag_incremental_notify.py`, `src/rag_*.py`. 수정 필요 시 RAG 담당과 조율.

## 2. 아키텍처 — 왜 이렇게 생겼나 (모르면 되돌리고 싶어지는 결정들)

| 결정 | 이유 |
|---|---|
| 수집은 HTML 파싱이 아니라 **REST API** (`src/member_api.py`, `CafeMemberNetworkArticleListV3`) | 2026-07-02 네이버가 멤버 글목록을 SPA로 전환 → HTML 파싱 0행. 커밋 `36a7746` |
| 로그인 판별의 **유일한 권위 = API code 0004** (`check_member_login`) | SPA 셸엔 article-board 마커가 항상 있어 HTML 휴리스틱이 원리적으로 무력 |
| `browser.py`의 article마커 우선/NotLoggedInError 무시/비공개배지 무시 | **테스트로 못박힌 의도적 결정.** 버그처럼 보여도 고치지 마라(리뷰에서 검토·기각됨) |
| `BrowserSession` 기본 = persistent context(`state/browser_profile`) | 로그인 쿠키 디스크 유지 → 무인 재시작. **프로필은 동시 1프로세스만**(수집기 2개 금지) |
| 무인 경로는 `--realtime-index` **인프로세스**뿐 | subprocess 경로는 대화형 로그인 프롬프트가 캡처 파이프에 묻혀 무한 정지 |
| 에러 분류 `member_api.is_block_error()` = **prefix 매칭** | 차단(login_required/captcha/no_permission/age_verification/`member_api_error code=`)만 중단+알림, 일시오류(소켓/5xx)는 3회 재시도 후 그 주기만 접고 루프 유지. substring으로 바꾸면 응답 body 오탐 재발 |
| 로그 쿠키 이중방어: `member_api._clean_error()`(Call log 제거) + `redact_secrets()`(기록 시 마스킹) | Playwright 예외 문자열에 NID_AUT/NID_SES 세션쿠키가 평문 포함(세션 탈취 위험). 과거로그 정리는 `scripts/scrub_log_secrets.py`(오늘 로그는 라이브 append 레이스 때문에 스킵함) |

**상주 루프** `scripts/run_daily_archive_loop.py` (`market_schedule_decision`, 코드와 일치 검증):
08-16시 300s / 16-18시 600s / 18-23시 1800s / **23-06시 중단** / 06-07시 1800s / 07-08시 600s.
사이클 = 제목수집(`index_tail_realtime.run_realtime_index`) + 본문수집(`batch_recollect`, 무인은 `interactive=False`).

## 3. 운영 — 작업 스케줄러 태스크 3종

| 태스크 | 트리거 | 하는 일 |
|---|---|---|
| `Archive-CollectLoop` | 로그온 시 | 상주 수집 루프. 런처 `scripts/start_archive_loop_boot.ps1`(HEADLESS=true·영구 duration·stale lock 청소·멘토 URL 내장). 실패 시 15분 재시작 |
| `Archive-Watchdog` | **1시간마다** | 죽었으면 안전 재기동: State 이중확인(TOCTOU) → **루프 python만 명령줄 매칭 kill**(RAG/요약 python 보호) → chrome 정리 → 재기동. 로그 `logs/watchdog.log`(자체 로테이션) |
| `Archive-DailySummary` | 매일 20:00 | `[Archive] 일일 수집 요약` 텔레그램. 오늘 건수 = **로그의 `[archive_loop] cycle N finished` 라인 saved_delta 합**(원문 앵커 — stdout_summary 이중카운트 방지). DB 풀스캔 아님(§5) |

**텔레그램**: RAG 인프라 재사용(전용봇 신설 안 함 — PM 결정). 루트 `.env`의 `RAG_TELEGRAM_BOT_TOKEN/CHAT_ID`(gitignore).
새 env 키 금지. 메시지 구분은 첫 줄 프리픽스: `[Archive] 세션 만료 감지` / `[Archive] 일일 수집 요약`.

**세션만료 알림**: `scripts/session_alert.py` + 루프 stop 경로 배선(`alert_on_session_expiry` @ run_daily_archive_loop).
code-0004 확정 + 1회 재프로브 → 발송. dedup = 최초 1회 + 24h 리마인더 + 발송실패 30분 하한. 상태 `state/session_alert.json`, 정상 사이클마다 리셋.

## 4. 운영 절차 (복붙용)

```powershell
# 통합 상태 확인(읽기 전용: Git·DB MAX(article_id)·상태/락·최근 사이클·태스크·프로세스)
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe scripts\archive_healthcheck.py
# 종료코드: 0=HEALTHY, 1=DEGRADED, 2=STOPPED. 자동 처리용 JSON은 --json.
# 실제 수집 활동을 함께 관찰하려면(증가 없음은 글이 없을 수도 있어 단독 실패로 판정하지 않음):
.\.venv\Scripts\python.exe scripts\archive_healthcheck.py --observe-seconds 60

# 개별 상태 확인
Get-ScheduledTask Archive-CollectLoop, Archive-Watchdog, Archive-DailySummary | Select TaskName, State
Get-Content state\archive_loop_status.json | ConvertFrom-Json | Select last_schedule_label, next_interval_seconds, last_return_code, last_saved, is_running, stop_reason

# 코드 배포 후 재시작(반영엔 재시작 필수)
# 모든 Python/Chrome을 이름만으로 종료하면 RAG 작업까지 죽을 수 있으므로 금지.
# docs/ARCHIVE_MINIPC_HANDOFF.md §4의 watchdog 일시차단 + Archive PID/자식 Chrome 선택 정리 절차를 실행한다.

# 네이버 재로그인 (세션만료 알림 왔을 때, headed 1회. "로그인 상태 유지" 체크 필수)
.\.venv\Scripts\python.exe scripts\daily_archive.py --login --login-check-retries 1 `
    --login-url "https://cafe.naver.com/ca-fe/cafes/29082876/members/THEA7uBzD6uKXKno57_Bl7jItzRnvmuDMltnPsGI9BY"
# 주의: --login 자체 검증은 HTML 방식이라 오탐 가능. 최종 판정은 아래 code-0004 프로브로.
# (프로브는 루프가 프로필을 잡고 있으면 충돌 — 루프 정지 후 실행)
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); from browser import BrowserSession; from member_api import check_member_login; s=BrowserSession(); print(check_member_login(s,'29082876','THEA7uBzD6uKXKno57_Bl7jItzRnvmuDMltnPsGI9BY')); s.close()"
```

`archive_healthcheck.py`는 애플리케이션 DB 내용·태스크·프로세스를 변경하지 않고 브라우저·네트워크도 열지
않는 **논리적 읽기 전용** 진단이다. 16GB DB는 read-only URI의 `MAX(article_id)`만 조회하며
`COUNT(*)`/`saved_at` 풀스캔을 하지 않는다. 단, 라이브 WAL DB를 읽는 SQLite 자체가 기존 `-shm`의 접근
시각·내용을 갱신할 수 있으므로 파일시스템까지 완전 무변경이라는 뜻은 아니다. 원본 명령줄과 원본 로그 대신
허용된 필드와 사이클 숫자만 보고하고, 상태 파일의 쿠키·토큰 문자열도 레닥션한다. 최신 3개 로그에서 최근
완료 사이클을 찾아 장외 시간(23-07시)은 10시간, 그 외에는 2시간 신선도 한도를 적용한다. 개발 PC처럼
Windows 시스템 진단이 불필요한 환경에서는 `--skip-system`을 사용할 수 있다. 장기 catch-up으로 완료
사이클이 오래됐어도 `--observe-seconds`에서 실제 DB/WAL 활동이 있고 CollectLoop·단일 수집기·락·세션이
모두 정상이면 신선도 경고만 보정한다. 이전 실패나 다른 경고는 보정하지 않는다.

**사람이 개입해야 하는 경우는 딱 둘**: ① 재부팅 후 Windows 로그인(자동로그인 미설정 — 오너 선택. 로그인해야 태스크가 뜬다),
② `[Archive] 세션 만료 감지` 수신 시 위 재로그인.

## 5. 환경 함정 (모르면 삽질)

- **`PYTHONUTF8=1` 필수** — cp949 로케일. 없으면 pytest 일부 실패·subprocess 읽기 크래시. 시스템 env 등록돼 있으나 새 셸에선 명시 권장. 테스트: `PYTHONUTF8=1 .venv\Scripts\python.exe -m pytest -q` (**기준선 667 통과**).
- **16GB DB, `saved_at` 인덱스 없음** — `WHERE saved_at` 풀스캔 2분+ 타임아웃. 일일 집계는 반드시 로그 합산 방식 유지. `saved_at`은 **UTC ISO**, 운영 기준시는 KST(경계 주의). `COUNT(*)`도 ~5초.
- **스냅샷 2026-05-02 고정** → 사이클마다 ~26페이지 재스캔(느릴 뿐 정상). realtime은 `--stop-after-empty-pages 5` 캡.
- pytest는 requirements.txt에 없음(수동 설치됨). python은 항상 `.venv\Scripts\python.exe`.
- `scripts/_step3_verify_v2.py` = 정체불명 미추적 파일. 커밋 금지(`git add -A` 쓰지 마라).
- 봇이 첫 재기동 사이클에서 밀린 글 catch-up 중이면 status가 수십 분 안 갱신될 수 있다 — 죽음 판정은 status 시각이 아니라 **DB max_id 증가**로 하라.

## 6. 개발 규칙

1. 별도 브랜치 → 구현 → **pytest 전체 통과** → **독립 코드리뷰(다각도) → 지적사항 수정·재검증** → 오너 확인 → main **ff-only** 반영 → (운영 코드면) 태스크 재시작 + 라이브 검증 → **파일:라인 근거 보고**.
2. **main force push 절대 금지. 커밋에 Co-Authored-By 금지.** git identity는 repo-local `Metrokid25`.
3. 수집 정본은 **`index_tail.py` 하나**다. `index_tail_realtime.py`는 기존 스크립트/import 경로를 보존하는
   호환 shim이며 수집 로직을 추가하지 않는다. 실시간 기능도 `index_tail.run_realtime_index`에서 수정한다.
4. HANDOFF.md는 대장 — 세션 종료 시 **맨 위에 새 항목**.

## 7. 사건 이력 (같은 실수 반복 금지)

| 일자 | 사건 | 교훈/조치 |
|---|---|---|
| 07-05 | 로컬 refs 138커밋 stale인 채 "상대 인프라 없음" 오판 | **git fetch 먼저**, 요약 말고 코드로 |
| 07-06 | 네트워크 순단(socket hang up)을 차단으로 오분류 → 루프 사망 반복 | `is_block_error` 분류기(§2) |
| 07-06 | Playwright 예외로 세션쿠키가 로그에 평문 유출 | `_clean_error`+`redact_secrets`+scrub(§2) |
| 07-15 | **0xC000013A**(세션 kill)로 봇 사망 → at-logon 트리거라 **3일 방치**, python 좀비 6개 | `Archive-Watchdog` 신설(§3). 일일요약 "0건"이 사망 신호였음 |
| 07-18 | 리뷰에서 워치독 이중인스턴스 위험(python 좀비 미정리+lock 무조건 삭제) 등 3건 | 워치독 재작성·요약 앵커링·scrub 가드(`7d01def`) |
| 07-22 | `index_tail.py`/`index_tail_realtime.py` 포크 divergence 위험 제거 | `index_tail.py` 단일 정본 + realtime 호환 shim. 무인 루프도 정본 직접 import |
| 07-23 | 배포용 워치독 잔류 검사기가 maintenance PowerShell 자기 자신을 워치독으로 오인해 안전 중단 | 프로세스 필터에서 현재 `$PID` 제외. 실제 워치독 잔류 탐지는 유지 |

## 8. 알려진 잔여 이슈 (검토됐고 의도적 보류 — 재발견에 시간 쓰지 마라)

1. `find_tail`/`_create_snapshot`은 일시오류를 아직 fatal 취급 — **수동 양산 모드만** 해당(데몬 경로 무관).
2. msvcrt Enter-wait 4중 복제 / `daily_archive.fetch_list_rows` 죽은 코드 ~115줄 / `build_daily_archive_command` 미사용.
3. `batch_recollect --estimate 2828`이 15개/페이지 기준(API는 20) — 실시간 수집 무영향.
4. 워치독·CollectLoop 모두 로그온 세션 필요 — **완전 로그오프 상태는 여전히 사각**(재부팅 후 로그인 규칙으로 커버).

## 9. main 이력 요약 (최신 위)

`7d01def` 리뷰 하드닝(요약 이중카운트·scrub 레이스·워치독 동시성) / `6e56cc2` 워치독 / `f542028` 일일 20시 요약 /
`4a30b0d` 로그 스크럽 유틸 / `da65a88` is_block_error 정밀화 / `2b60fc8` 루프 리질리언스+쿠키누출 수정 /
`8e3ff77` 세션만료 알림 하드닝 / `46c1e82` 세션만료 알림 / `fd77e96` 부팅 런처(HEADLESS) /
`bd06136` **수집 계층 재통합**(분수령) / `63509d6` 리뷰 버그 6건 / …이전은 RAG 계층(`deploy-baseline-20260705`).
