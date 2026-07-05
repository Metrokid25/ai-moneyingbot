# 인수인계 대장 (PC ↔ 노트북)

> 작업 세션이 끝날 때 **맨 위에 새 항목**을 추가한다(최신이 위). 다른 기계에서 이어받는 Claude/사람이
> 이 파일만 읽으면 "직전에 뭘 했고, 산출물이 어디 있고, 다음에 뭘 할지"를 안다.
> - 규칙: 데이터/정책 = MACHINE_SYNC.md, 세션별 진행 = 이 파일, 결과물 상세 = `docs/*.md`.
> - 이 파일과 `docs/`는 git-tracked → commit+push 해야 다른 기계가 본다. (`data/`의 mentor.db·qdrant는 수동 이관)

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
