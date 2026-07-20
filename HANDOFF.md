# 인수인계 대장 (PC ↔ 노트북)

> 작업 세션이 끝날 때 **맨 위에 새 항목**을 추가한다(최신이 위). 다른 기계에서 이어받는 Claude/사람이
> 이 파일만 읽으면 "직전에 뭘 했고, 산출물이 어디 있고, 다음에 뭘 할지"를 안다.
> - 규칙: 데이터/정책 = MACHINE_SYNC.md, 세션별 진행 = 이 파일, 결과물 상세 = `docs/*.md`.
> - 이 파일과 `docs/`는 git-tracked → commit+push 해야 다른 기계가 본다. (`data/`의 mentor.db·qdrant는 수동 이관)

---

## 2026-07-18 · 미니PC · main `7d01def` (Archive봇 — 무인 운영 안착)

**한 일 (07-06~18, 상세는 `docs/ARCHIVE_MINIPC_OPERATIONS.md` — Archive 운영 기준 문서 신설)**
- **미니PC 무인 수집 라이브**: 상주 루프를 작업 스케줄러 3태스크로 배포 — `Archive-CollectLoop`(로그온·헤드리스·market schedule), `Archive-Watchdog`(1시간, 사망 시 안전 재기동), `Archive-DailySummary`(매일 20:00 수집량 텔레그램).
- **세션만료 텔레그램 알림**(`scripts/session_alert.py`): code-0004 확정+재프로브 → `[Archive] 세션 만료 감지`. RAG 텔레그램 재사용(전용봇 신설 안 함 — PM 결정, `.env`의 RAG_TELEGRAM_* 재사용). dedup 24h+실패 30분 하한. 실발송 검증 완료.
- **루프 리질리언스**: 네트워크 순단을 차단으로 오분류해 루프가 죽던 문제 → `member_api.is_block_error()`(prefix 분류) 도입, 일시오류는 재시도 후 루프 유지. 8일 연속 무중단 실증.
- **보안**: Playwright 예외의 세션쿠키(NID_AUT/NID_SES) 로그 평문 유출 차단(`_clean_error`+`redact_secrets`) + 과거 로그 스크럽.
- **07-15 사고**: 0xC000013A(세션 kill)로 봇 3일 사망(일일요약 "0건"이 신호였음) → 복구 + 워치독 신설. 이후 리뷰에서 워치독 이중인스턴스 위험 등 3건 발견·수정(`7d01def`).
- 테스트 기준선 **667 통과**(PYTHONUTF8=1 필수).

**미니PC가 이어받으려면**
1. `git fetch` + `docs/ARCHIVE_MINIPC_OPERATIONS.md` 정독(아키텍처 결정 이유·환경 함정·사건 이력 포함).
2. 사람 개입은 둘뿐: 재부팅 후 Windows 로그인 / `[Archive] 세션 만료 감지` 수신 시 headed 재로그인 1회.

**다음 작업 (보류 중, 급하지 않음)**
- index_tail 포크 통합 · find_tail/_create_snapshot 일시오류 분류 · Enter-wait 4중복 정리 (운영 문서 §8).

---

## 2026-07-05 · 미니PC · 브랜치 `integrate/collection-into-main` (Archive봇)

**한 일**
- **수집 계층 재통합**: `archive-agent-auto-work`(수집 하드닝 46커밋, 분기점 `3420185` 2026-05-29)를 RAG 138커밋이 안착된 main 위에 머지. main만으로는 수집이 구 HTML 파싱 경로(SPA에서 0행)라 미니PC 무인 수집이 불가능했던 갭을 해소.
- 편입된 수집 계층: REST API 수집(`src/member_api.py`, code 0004 로그인 판별) · persistent browser context(`src/browser.py`) · 운영 루프(`scripts/run_daily_archive_loop.py`, market schedule, lock) · 실시간 인덱싱(`scripts/index_tail_realtime.py`) · 런처 ps1 3종.
- RAG 계층(notify_telegram / run_rag_incremental_notify / 스키마)은 main 버전 그대로 유지. 단 `src/rag_chunking.py`의 `parse_year_month`에 ISO 날짜 파싱 추가분이 자동 머지로 편입됨 — member_api 경로가 `posted_at`을 `YYYY-MM-DD HH:MM:SS`로 저장하므로 필수 동반 수정(없으면 신규 글 year/month 전부 null).

**다음 작업**
- 형(오너) 확인 후 main 반영. force push 금지 유지.
- 미니PC 무인 수집 스케줄 + 세션만료 텔레그램 알림(Archive 전용 봇)은 별도 후속 작업.

---

## 2026-07-05 · 노트북(개발) · 브랜치 `agent/rag-ingest-boundary`

**한 일**
- **3-봇 데이터 소유권 계약 문서화** → `docs/OWNERSHIP.md` (`2ccb2ec`): 원본코퍼스=Archive / 파생 Qdrant인덱스=RAG / 매매상태=trading-bot. repo 분리 유지, 연동은 API/JSONL 경계, 교차키 `article_id`. (검토용 INTEGRATION_PROPOSAL은 폐기 `84d1aea`.)
- **RAG 증분색인(incremental indexing) 무인 러너 완성** (`28d07e3`):
  - `scripts/run_rag_incremental_notify.py` — 색인 실행→결과 파싱→재시도(rc=2 제외)→텔레그램 통지. 무인 크래시 방지(utf-8 errors=replace, try/except).
  - `scripts/notify_telegram.py` — RAG **전용** 텔레그램 봇(=`Rag-bot`, trading-bot과 별개 · OWNERSHIP).
  - `scripts/register_rag_index_schedule.ps1` — Windows 스케줄러 등록, **LogonType S4U**(로그오프에도 실행).
  - `docs/DEPLOY_MINIPC.md` — 미니PC 배포 절차(clone→venv→.env→data 이전→스케줄→검증) + 트러블슈팅.
  - 독립 코드리뷰 **2라운드** 반영, 테스트 14개. 텔레그램 문구 평문화(`indexing`).
- **무인 검증 완주 실증**: 스케줄러 **자동발화**(15:03, 사람 손 X) → 합성글 1청크 임베딩 → 테스트 Qdrant 적재(points=1) → 텔레그램 수신, 결과코드 0.

**한 일 (후반 — PM 지시 4건)**
- **텔레그램 토큰 재발급 완료**: 노출 토큰 `/revoke` → 구 토큰 401 확인, 새 토큰(`@moneying_rag_index_bot`) 실수신 재검증. 새 토큰은 `.env`에만 존재(채팅 미노출).
- **main 병합 완료**: `agent/rag-ingest-boundary` 133커밋 → main (`0410f88`, 무충돌, 507 테스트 통과). 이후 생존신호 브랜치 병합(`c8892a3`, 512 테스트 통과). **main 직접 커밋 금지 규약 유지 — 변경은 항상 `agent/rag-*` 브랜치→승인→병합.**
- **배포 기준점 태그 규약 신설(PM 확정)**: 태그 `deploy-baseline-20260705` = `c8892a3`. 향후 기준점 갱신도 `deploy-baseline-YYYYMMDD` 태그 표준.
- **수집 생존 신호 구현(PM 요구)**: 색인 텔레그램 통지에 "마지막 수집글 작성일"(archive.db 읽기전용 probe) 포함 → "신규 0건"이 진짜 없음인지 수집 死인지 문면으로 구분. probe 실패 시 `확인불가`(무인 크래시 없음).
- **Archive봇 협의 프롬프트 최종본 제출**: 세션 지속(storage_state)·만료 시 텔레그램 알림·무인 수집 스케줄·서킷브레이커 검토 + 결정 3건. **오너가 Archive봇 담당 세션에 전달할 것.**

**미니PC가 이어받으려면**
1. `git pull` → **`main` 체크아웃** (배포 기준점: 태그 `deploy-baseline-20260705` = `c8892a3`).
2. `docs/DEPLOY_MINIPC.md` 그대로 수행. **단, 미니PC 배포는 PM 지시로 대기 중** — trading-bot 모의투자 안정 가동(2~3일 관찰) 후 PM이 시점 지시.
3. `.env` 필요값: `VOYAGE_API_KEY`, `RAG_TELEGRAM_BOT_TOKEN`, `RAG_TELEGRAM_CHAT_ID`(=`@moneying_rag_index_bot` 재발급 토큰 / 오너 chat_id). `data/qdrant/` + `data/rag_index_manifest.jsonl`(또는 seed ids) **수동 이관**(gitignore).

**⚠️ 의존성 — Archive봇이 정상 작동해야 전체가 산다 (미해결, 내 소유 밖)**
- 색인 봇은 `archive.db`에 **새 글이 쌓여야** 의미가 있다. 수집(크롤링·네이버 로그인)은 **Archive봇 소관**.
- 현재 수집 코드(`src/browser.py`)는 **매 실행 수동 로그인 필요**(세션 미저장) → 미니PC **무인 수집은 아직 미구현**.
- 색인 봇은 "수집 실패로 0건"과 "진짜 0건"을 **구분 못 함** → `신규 0건`이 실제론 수집 死일 수 있다.
- **→ PM / Archive봇 담당 액션 필요:** 네이버 로그인 **세션 지속(storage_state)** + 무인 수집 스케줄. 이게 되어야 색인 봇 알림이 진짜 의미를 가진다.

**다음 작업**
- ~~텔레그램 토큰 재발급~~ → **완료** (후반 참고).
- Archive봇 협의 회신 대기 → 인터페이스 합의까지가 RAG 역할 (수집 구현은 Archive봇 몫).
- 미니PC 배포: **PM 지시 대기** (trading-bot 모의투자 안정화 후). 그 전까지 DEPLOY 문서 유지보수만.
- 검색 API 구현·Phase 2 잔여 배치·대규모 리팩토링: 계속 보류(PM 지시).

---

## 2026-07-02 · PC · 브랜치 `archive-agent-auto-work` (Archive봇)

**상태: 아카이브봇 정상 작동 (검증 완료)**

네이버가 멤버 작성글 목록(/f-e/, /ca-fe/)을 클라이언트 렌더 SPA로 바꿔 HTML 파싱이 0행이 됐던 고장을 **REST API 직접 호출 방식으로 전환**해 해결. 커밋 `36a7746`.

- 제목 수집: `apis.naver.com/cafe-web/cafe-mobile/CafeMemberNetworkArticleListV3` (SPA 번들에서 확인한 실제 API). 클라이언트: [src/member_api.py](src/member_api.py)
- 로그인 판별의 신뢰 근거는 이제 이 API의 `code 0004` (HTML 휴리스틱은 SPA 셸에서 무력).
- 실검증: 밀린 제목 36건 + 본문 36/36 수집 성공. DB 43,491건 / max_id 172512. 테스트 306개 통과.
- 8각도 독립 리뷰 → 12건 검증 → 확정 문제 전부 수정 → 재리뷰 클리어.

**운영 방법**
`run_archive_bot_local.ps1` 한 번만 실행. 이미 로그인돼 있으면 Enter 없이 시작(무인 재시작 가능). 로그인 풀리면 명확히 멈추고 로그인 페이지를 열어줌.

**주의사항**
- 네이버 로그인 시 **"로그인 상태 유지" 반드시 체크** (안 하면 브라우저 종료 시 세션 소멸).
- 봇 강제종료 시 `state\archive_loop.lock`이 남아 30분간 재실행 차단 → 파일 삭제 후 재실행.
- venv python + 시스템 python 2개 프로세스로 보이는 건 정상(부모+자식), 중복 실행 아님.

**남은 개선 후보 (급하지 않음)**
- 백로그 모드 `--estimate 2828` 기본값이 15개/페이지 기준 → API는 20개/페이지라 재보정 필요 (실시간 수집엔 영향 없음).
- captcha/본인인증 등 비로그인 차단신호가 API 경로에선 미분류(generic error)로 뭉개짐.
- index_tail.py / index_tail_realtime.py 중복 → 공용 모듈로 통합하면 다음 네이버 변경 시 한 곳만 수정.
- 스냅샷이 2026-05-02 고정이라 collect-after-snapshot이 매번 ~26페이지 재스캔 (결과는 정상, 약간 느릴 뿐).

---

## 2026-07-02 · PC · 브랜치 `agent/rag-ingest-boundary`

**한 일**
- RAG 검색 품질 첫 실측 — 리랭킹이 recall@1 0.40→0.80, MRR 0.54→0.88 (`c7def86`, 러너 `scripts/evaluate_rag_recall_gold.py`, gold셋 `tests/fixtures/rag_eval_questions_corpus.jsonl` `c760b42`).
- 스승님 매매패턴 추출 → **`docs/trading_rules_codified.md`** 에 R1~R6 + 표준셋업(#89519) 코드화 + AI 코딩 프롬프트 + 원문 링크.
- 노트북 코퍼스 DB: **`scripts/build_mentor_db.py`** → `data/mentor.db`(42,947글 전체 clean_text, LIKE+FTS, 170MB). MACHINE_SYNC §3·§6에 정책 반영 (`76ca188`).

**노트북이 이어받으려면**
1. `git pull` (브랜치 `agent/rag-ingest-boundary`).
2. `data/mentor.db`(170MB), `data/qdrant/`(600MB) 수동 복사(읽기 전용). ← git 안 됨.
3. 트레이딩봇 시작점 = `docs/trading_rules_codified.md`의 AI 코딩 프롬프트. 그 안 "모호점 5개" 먼저 확정.

**다음 작업(우선순위)**
1. 트레이딩 규칙 백테스트 엔진 스켈레톤 — 모호점 5개 확정 후.
2. **주가 데이터(OHLCV) 소스 확보** — pykrx 등. (실제 병목: 아카이브엔 주가가 없음)
3. RAG 쪽 잔여: 소프트스폿 문항 교체 / fetch_k 스윕 (MACHINE_SYNC §4).

**열린 결정**
- 세션-종료 자동 인수인계(훅) 방식 미확정 — 아래 후속 논의.
