# 인수인계 대장 (PC ↔ 노트북)

> 작업 세션이 끝날 때 **맨 위에 새 항목**을 추가한다(최신이 위). 다른 기계에서 이어받는 Claude/사람이
> 이 파일만 읽으면 "직전에 뭘 했고, 산출물이 어디 있고, 다음에 뭘 할지"를 안다.
> - 규칙: 데이터/정책 = MACHINE_SYNC.md, 세션별 진행 = 이 파일, 결과물 상세 = `docs/*.md`.
> - 이 파일과 `docs/`는 git-tracked → commit+push 해야 다른 기계가 본다. (`data/`의 mentor.db·qdrant는 수동 이관)
>
> **노트북 Archive 작업자 시작점**: 별도 채팅 프롬프트는 필요 없다. Archive 전용 worktree에서
> `git status --porcelain=v1`이 비어 있는지 먼저 확인하고 `git pull --ff-only origin main`을 실행한 뒤,
> `docs/ARCHIVE_NOTEBOOK_HANDOFF.md`를 처음부터 끝까지 읽고 따른다. 출력이 있거나 pull이 실패하면 멈춘다.

---

## 2026-08-07 · 미니PC 운영 배포 · main `5475156` (1시간 재알림 + 장외 세션 keepalive 라이브 검증)

**반영**
- 오너 지시로 세션 만료 성공 알림을 24시간에서 1시간 주기로 바꾼 `3fb7b18`을 작업 브랜치와 원격
  `main`에 fast-forward 반영했다. 이어진 `5475156`은 이 커밋을 포함하며 23:00~06:00 수집 중단 중에도
  동일 persistent 세션에서 멤버 REST API keepalive를 최대 1시간 간격으로 수행한다.
- 미니PC 운영 checkout을 `ead7188 → 3fb7b18 → 5475156`으로 ff-only 갱신했다. 보호 대상 미추적
  `scripts/_step3_verify_v2.py`는 그대로 보존했고 RAG runtime·다른 Python은 수정하거나 종료하지 않았다.
- Watchdog을 일시 차단하고 Archive PID/자식 Chrome만 선택 정리했다. 첫 종료 검증은 프로세스 소멸 반영이
  늦어 fail-closed됐지만 후속 조회에서 잔여 PID 0을 확인했고, 예약 재시작 후 08:50 단일 controller로 안착했다.

**라이브 검증**
- 배포된 `session_alert.REMINDER_INTERVAL_HOURS=1.0`, 기존 06:00 만료 상태에 대한
  `should_send(...)=True`를 읽기 전용으로 확인했다. 실제 텔레그램 강제 발송은 하지 않았다.
- 로그인 복구 후 DB `max(article_id)`는 173921→173972로 증가했고 최신 표본은 모두
  `BODY_COLLECTED`, `attempt_count=1`, 오류 없음이다.
- 첫 정상 회차는 08:50:47~09:20:52, `returncode=0`, `latest_id=173972`; 성공 후
  `state/session_alert.json`이 자동 삭제됐다.
- 사후 60초 healthcheck는 `HEALTHY`, rc=0. controller instance 1개, CollectLoop Running,
  Watchdog 09:23 자동발화 결과 0, DailySummary 정상 대기, `HEAD == origin/main == 5475156`이다.

**남은 자연 검증**
- 1시간 재알림은 다음 실제 code-0004 지속 상황에서 확인한다. 장외 keepalive의 서버측 세션 유지 효과는
  23:00~06:00 경계를 한 번 통과한 뒤 다음날 06시 REST 수집 성공 여부로 확인한다.

---

## 2026-08-07 · 미니PC · 브랜치 `agent/archive-offhours-session-keepalive-20260807` (장외 세션 keepalive)

**운영 사고와 복구**
- 08-05 headed 재로그인 후 정상 수집됐지만 23:00~06:00 무요청 구간을 지난 08-06 06시 첫 REST 요청부터
  `member_api code=0004`가 반복됐다. 로컬 쿠키 만료값과 별개로 서버측 유휴 세션이 끊긴 정황이다.
- 08-07 headed 재로그인, persistent 프로필 재개방 API 프로브, CollectLoop 재기동을 완료했다. DB max id가
  173921→173972로 증가했고 단일 controller·락·headless 프로세스가 정상임을 확인했다.

**재발 방지 변경**
- 23:00~06:00 글 수집 중단은 유지하면서 persistent realtime 세션에서만 멤버 REST API 로그인 프로브를
  최대 1시간 간격으로 수행한다. HTML 파싱이나 별도 subprocess를 사용하지 않는다.
- `True`는 알림 상태를 리셋하고 대기, 일시오류 `None`은 루프를 유지해 다음 시간에 재시도, code-0004 확정
  `False`는 기존 세션만료 알림 후 종료한다. `is_block_error`와 browser 로그인 휴리스틱은 변경하지 않았다.
- 원격 main의 별도 변경 `3fb7b18`(만료 지속 중 1시간마다 재알림)을 먼저 ff-only 반영해 함께 검증했다.

**검증과 상태**
- 집중 테스트 82 passed, 전체 suite 765 passed (`PYTHONUTF8=1`), `py_compile`과 `git diff --check` 통과.
- 정확성·운영 결합·일시오류·보안 관점 리뷰에서 확정 문제를 수정했고 P0~P3 잔여 없음.
- 변경은 별도 worktree에 미커밋 상태다. 오너 승인 전 commit/push/main 반영/운영 재시작은 하지 않는다.
- 실제 서버 세션 유지 효과는 23:00~06:00 경계를 한 번 통과한 뒤 다음날 06시 라이브 검증이 필요하다.

---

## 2026-08-05 · 미니PC · 브랜치 `agent/archive-hourly-session-reminder-20260805` (세션 만료 매시간 재알림)

**변경**
- 새벽 06:00에 `member_api code=0004`로 Archive 수집이 중단됐지만 기존 24시간 dedup 때문에 후속 알림이
  없었던 운영 사례를 반영해, 세션 만료 성공 알림의 기본 리마인더 간격을 24시간에서 **1시간**으로 변경했다.
- 최초 알림, 59분 이내 억제, 정확히 60분 후 재알림, 만료 지속 시 이후 매시간 재알림을 테스트로 고정했다.
- 로그인 판정(`check_member_login`의 code 0004), 1회 재프로브, 발송실패 30분 하한, 정상 복귀 시 상태 리셋,
  RAG 텔레그램 재사용과 시크릿 방어는 변경하지 않았다.

**검증·리뷰**
- 집중 테스트 `33 passed`, 전체 suite `762 passed in 32.05s`, 모두 `PYTHONUTF8=1`, rc=0.
- `git diff --check` rc=0. 실제 Watchdog 트리거 `PT1H`를 확인해 만료 지속 중 매시간 재프로브·재알림 경로가
  성립함을 검증했다.
- 정확성·운영 결합·실패 백오프·보안/소유권 관점 리뷰에서 P0~P3 없음. 변경은 Archive 알림 코드·테스트·
  운영문서와 이 인수인계 항목에만 한정했다.

**상태/다음 단계**
- 변경은 별도 worktree에 미커밋 상태다. 오너 확인 전 commit/push/main 반영/운영 태스크 재시작은 하지 않는다.
- 승인 후 main ff-only 반영 → 미니PC Archive 운영 checkout ff-only 갱신 → 안전 재시작 → healthcheck와 실제
  시간 경계 알림을 라이브 검증한다. 현재 code 0004 세션 만료는 별도 headed 재로그인이 필요하다.

---

## 2026-08-03 · 미니PC 운영 배포 · 태그 `deploy-baseline-20260803` / commit `3fec893` (RAG 증분색인 실가동)

**배포 결과**
- 오너 승인 범위로 Rulebook 연구 계약 2커밋(`887cb1c`, `f71593f`)과 RAG 운영 하드닝
  `3fec893`을 독립 리뷰 후 `main`에 fast-forward 반영했다. 배포 코드 기준점은 annotated tag
  `deploy-baseline-20260803`이며 commit은 `3fec893e11675f9ba49d535d4adff21d000170a7`이다.
- 미니PC에 clean 운영 worktree `C:\projects\naver_cafe_archive_rag_runtime`를 만들고
  `runtime/rag-deploy-20260803` / HEAD `3fec893`으로 고정했다. Python 3.12 venv와 requirements를 설치하고
  기존 `.env`의 필수 3키를 값 노출 없이 복사·비어 있지 않음만 확인했다.
- Archive 소유 DB는 `C:\projects\naver_cafe_archive\data\archive.db`를 읽기 전용으로 사용한다.
  RAG 소유 Qdrant와 manifest는 기존 안전 자산
  `C:\projects\naver_cafe_archive_rag\data\qdrant`,
  `C:\projects\naver_cafe_archive_rag\data\rag_index_manifest.jsonl`을 그대로 사용한다.

**안전 게이트·실행 실측**
- 배포 전 자산 게이트: `status=PASS`, Archive `sqlite_query_only=true`, manifest/Qdrant 각각 51,040,
  collection `goodmorning_chunks`, vector 1024/Cosine, ID 집합 일치, `write_performed=false`.
- 공식 dry-run: `rc=0`, 현재 51,047 / 반영 51,040 / 신규 7청크, 마지막 수집글 작성일
  `2026-08-03 09:48:14`; manifest SHA-256
  `25F120425279B49FDA0C8EB91179DD4000C999C52F8434BE1A2297CA8BB879DF`와 수정시각 모두 불변이었다.
- 기존 예약 작업 XML은
  `C:\Users\미니PC\AppData\Local\Temp\RAG-IncrementalIndex-pre-20260803.xml`에 백업했다.
  `RAG-IncrementalIndex`를 새 runtime의 Python/wrapper로 재등록했으며 S4U, 16:30 매일,
  DB/Qdrant/manifest 절대경로, 2시간 제한을 사용한다.
- `2026-08-03 10:11:47 KST` 수동 예약 실행은 `Ready`, `LastTaskResult=0`, writer 0으로 종료됐다.
  후속 자산 게이트도 `status=PASS`: manifest 51,047줄, Qdrant 51,047포인트, unique 51,047,
  ID 집합 일치, 최대 반영 article_id 173760, `write_performed=false`다.
- 새 runtime과 구 체크아웃 모두 tracked clean이다. 구 체크아웃
  `C:\projects\naver_cafe_archive_rag` / HEAD `06b5b68`은 롤백용으로 보존했으며 삭제·reset하지 않았다.

**검증·다음 확인**
- 연구 계약 독립 clean-worktree 전체 `759 passed`; 운영 하드닝 통합 전체 `761 passed`,
  PowerShell AST 오류 0, `git diff --check` rc=0, 실제 시크릿 패턴 0건이었다.
- 다음 필수 확인은 `2026-08-03 16:30 KST` 첫 자동발화 후 `LastTaskResult=0`, manifest/Qdrant 일치,
  텔레그램 수신 여부다. 이 자동발화까지 성공하기 전에는 롤백 체크아웃과 작업 XML 백업을 제거하지 않는다.
- 검색 API, Phase 2 잔여 대량 배치, trading-bot 데이터 접근은 이번 범위에 없었고 계속 보류한다.

---

## 2026-08-03 · 데스크톱+미니PC 읽기전용 · 브랜치 `agent/rag-trading-research-contract-20260803` (A등급 연구 계약·Rulebook RAG 실측)

**결과**
- Rulebook v2 자동화 A등급 `GM-R01/R03/R06/R07`을 Trading Bot이 독립 검증할
  `artifacts/trading_research/a_grade_rules_research_contract_v1.jsonl`을 만들었다.
  baseline·후보 grid·시계열 walk-forward·봉인 holdout·비용 stress·룩어헤드 방지·결과 반환 schema를
  고정했으며 자동 적용과 실거래 승인은 false다. RAG는 Trading Bot 소유 데이터에 접근하지 않았다.
- 12개 규칙마다 core 1개+caveat 1개인 24문항 gold를
  `tests/fixtures/rag_rulebook_gold_v2.jsonl`로 만들었다. 24개 지정 article/chunk는 전부 Rulebook 근거다.
- 생성·검증·진단 도구 4개와 테스트 14개, 운영·연구 문서 5개를 추가했다. 상세 시작점은
  `docs/TRADING_RESEARCH_HANDOFF_A_GRADE.md`, `docs/RAG_RULEBOOK_LIVE_EVAL_20260803.md`,
  `docs/RULEBOOK_V2_DECISION_GATE_20260803.md`다.

**production RAG 실측**
- 미니PC `C:\projects\naver_cafe_archive_rag`의 manifest 51,040줄에서 gold 청크 24/24를 확인했다.
  Qdrant UUID 직접 조회도 24/24 존재, article_id 불일치 0, 빈 text 0이었다.
- 24문항 dense→Voyage rerank 1회 결과: dense recall@1/5/10=`0.4583/0.7083/0.8333`,
  MRR@10=`0.5678`; rerank=`0.8333/0.8750/0.8750`, MRR@10=`0.8542`.
- rerank 지정근거 미회수 3건은 GM-R01 최신 근거의 실제 fetch-50 미회수, GM-R02 동의 근거 중복으로
  지정 ID가 밀린 사례, GM-R11 예외 근거 미회수로 분리했다. fixture는 결과에 맞춰 변경하지 않았다.
- 라이브 JSON은 `artifacts/rulebook_v2/evaluation/` 3개 파일에 보존했다. 미니PC에는 `%TEMP%` 파일만
  썼고 로컬 복사 후 정확한 8개 임시 파일을 삭제했다. DB/Qdrant/manifest/태스크/시크릿은 변경하지 않았다.
- Rulebook Archive union 재검증: 12규칙, 고유 article 24개, 원문 인용 36/36,
  `archive_union_count=43789`, `query_only=true`, rc=0.

**운영 하드닝 독립 리뷰**
- 원격 `3821e23`의 WindowsIdentity 기반 스케줄 계정과 `article_id DESC` 생존신호 변경에서 P0~P2를
  찾지 못했다. 커밋 자체 표적 `40 passed`, 최신 `origin/main=2df7479` 격리 적용 전체
  `747 passed`, PowerShell AST 오류 0, diff check 0, merge-tree 충돌 없음이다.
- 미니PC 실제 RAG checkout은 아직 HEAD `06b5b68`, `ahead 2 / behind 9`이며 구버전
  `$env:USERDOMAIN\$env:USERNAME`, `ORDER BY saved_at DESC`를 사용한다. 현재 태스크는 정상이나 하드닝
  통합·deploy baseline 확정·별도 배포 승인 전에는 checkout/pull/스케줄을 변경하지 않는다.
- 리뷰 정본: `docs/RAG_OPS_HARDENING_REVIEW_20260803.md`.

**검증/Git 상태**
- 새 표적 테스트 `14 passed in 0.55s`, 현재 브랜치 전체 `758 passed in 16.34s`, py_compile rc=0,
  `git diff --check` rc=0, 신규 파일 18개 시크릿 패턴 0건.
- 현재 브랜치는 Rulebook commit `edfee47`에서 분기했고 변경은 아직 미커밋·미푸시다.
  확인 시 `origin/main=2df7479`, main 고유 1/현재 HEAD 고유 1이며 main은 현재 브랜치 조상이 아니다.
- 다음: 오너가 커밋·푸시를 승인하면 작업 브랜치에서만 커밋 → 최신 main과 안전 통합 → 전체 재검증 →
  독립 리뷰. 운영 하드닝 main 통합과 미니PC 배포는 별도 승인으로 진행한다. Trading Bot 결과가 오기 전
  모든 규칙은 `research_hypothesis_unvalidated`를 유지한다.

---

## 2026-08-03 · 미니PC · `main` `ead7188` (Archive 지연 패치 반영·라이브 검증 완료)

**반영**
- 오너 승인 범위로 미니PC Archive checkout을 `52def4d → ead7188`로 ff-only 갱신했다.
- 운영 코드 변경은 Enter-wait 공용 helper 통합·죽은 코드 제거 `3105869`와
  stdin EOF fail-closed `b215465`를 포함한다.
- `docs/ARCHIVE_MINIPC_HANDOFF.md` §4대로 Watchdog을 일시 차단하고 Archive PID/자식 Chrome만
  선택 정리한 뒤 CollectLoop를 재시작했다. 선택된 Archive PID는 7개, 비Archive Python 종료는 0개다.

**라이브 검증 (2026-08-03 00:39 KST 사후 읽기전용 재확인)**
- 배포 전·후 60초 관찰 healthcheck 모두 `HEALTHY`, rc=0으로 보고됐고,
  사후 읽기전용 healthcheck도 `generated_at=2026-08-03T00:39:27+09:00`, `HEALTHY`, rc=0이다.
- 최종 `HEAD == origin/main == ead7188`, tracked clean, 알려진 미추적
  `scripts/_step3_verify_v2.py`만 존재한다.
- 보호 파일 SHA-256은 전·후
  `56CBA94517054572A8148F3A9EAB6218628884AC1103DF2F88488CF85719A2EA`로 동일하다.
- CollectLoop `Running`, Watchdog/DailySummary enabled·`Ready`, controller instance 1개,
  loop lock 정상, 세션 경고 없음, latest article ID `173739`. 최종 결론 `LIVE VERIFIED`.

**다음 단계**
- 신규 장애 없이 일상 수집을 관찰한다. 즉시 착수할 Archive 코드 과제는 없다.
- 완전 로그오프 사각지대는 작업 스케줄러·로그인 세션 구조 변경이므로 별도 설계·승인 전까지 보류한다.

---

## 2026-07-27 · 데스크톱+미니PC 4자 협업 · 브랜치 `agent/rag-rulebook-pdf-v2-20260727` (굿머닝 매매원칙 검증판 v2 제작)

**결과**
- 기존 `굿머닝_그림해설판.pdf`를 교육용 요약본으로만 사용하고, Archive 원문을 다시 대조해
  `output/pdf/굿머닝_매매원칙_검증판_v2.pdf` 23쪽을 생성했다.
- PDF는 12개 규칙을 시장 레짐→비중→진입→손절/익절 계층으로 정리한다. 각 카드에서
  선생님 직접 가르침과 연구자 구현 가설, 필요조건, 무효화, 예외, 데이터 요구사항을 분리했다.
- 구조화 정본은 `output/pdf/굿머닝_매매원칙_검증판_v2_rules.jsonl`이며, 12개 규칙,
  고유 근거 글 24개, 짧은 원문 인용 36개를 포함한다. 모든 상태는
  `research_hypothesis_unvalidated`이고 백테스트·수익성 검증 완료 주장은 없다.
- 재현 생성기는 `scripts/build_rag_rulebook_pdf_v2.py`, 사람이 편집하는 규칙 원본은
  `artifacts/rulebook_v2/rules_v2.json`, QA 기록은
  `output/pdf/굿머닝_매매원칙_검증판_v2_QA.json`이다.

**Archive/RAG 최신성 실측**
- 미니PC Archive는 SQLite `mode=ro`+`query_only=ON`으로만 조사했다. 현재 본문은 43,789건,
  최신 `article_id=173508`; 기존 PDF 표기 42,979건 대비 총량은 +810건이다.
- 데스크톱 DB 43,506건과 미니PC에서 stdout으로만 받은 신규 JSONL 283건의 article_id 중복은 0건,
  합집합 43,789건이다. 운영 DB·태스크·체크아웃에는 쓰기나 재시작을 하지 않았다.
- 미니PC RAG는 manifest/Qdrant 50,957청크, 공식 dry-run 현재 50,969청크로 신규 12청크·7개 글이
  정규 증분 전이었다. 최신 글은 semantic 검색 결과로 가장하지 않고 Archive 원문 직접검토로 반영했다.
  그중 `article_id=173480`의 불확실성·비중관리 가르침을 GM-R01 신규 근거로 채택했다.

**검증 출력**
- `PYTHONUTF8=1 python scripts/build_rag_rulebook_pdf_v2.py --check-only`
  → `validation=passed`, `rule_count=12`, `source_article_count=24`,
  `quote_checks_passed=36`, `archive_union_count=43789`, `query_only=true`, rc=0.
- 최종 빌드 → PDF 309,498 bytes, QA warnings 0, 자동화 등급 A/B/C=`4/6/2`, rc=0.
- Poppler 150/120dpi 렌더 → 23/23쪽, rc=0. 전체 접촉표와 표지·최신성 표·규칙 카드·색인 연속쪽·
  마지막 쪽 확대 검수에서 잘림·깨짐·빈 표 머리글 없음.
- `pypdf` → pages=23, empty_pages=0, GM-R01~GM-R12 전부 존재,
  article_id 173508/173480 존재.
- `python -m py_compile scripts/build_rag_rulebook_pdf_v2.py` rc=0,
  `git diff --check` rc=0.
- 독립 RAG 리뷰는 Archive/RAG 숫자, 가설 분리, 미검증 상태, 소유권 경계, 최신 미색인 설명이
  정확하다고 확인했다. 처음 지적된 validation 문구 QA 경고 7건은 문구를 명시화해 최종 0건으로 해소했다.
  독립 작업자의 렌더 도구는 중단됐으므로 시각 검수는 주 작업자가 23쪽 전체를 대신 완료했다.

**Git/다음 단계**
- 이 작업은 `origin/main=ead7188`에서 만든 격리 브랜치에서 진행했다. 오너 승인으로 이 항목과 산출물을
  작업 브랜치에 커밋·푸시했으며 `main`에는 병합하지 않았다.
- trading-bot 데이터 접근·연동·백테스트는 이번 범위에 없었다. 다음 연구는 A등급 위험관리 규칙부터
  별도 승인 후 진행한다.

---

## 2026-07-27 · 노트북+미니PC 읽기전용 · `main` `b215465` (Archive main 반영·RAG 라이브 확인)

**Git/Archive**
- 오너 승인 범위에 따라 Enter-wait 통합 브랜치와 EOF 보강 브랜치를 원격에 push하고,
  최신 원격 `main`의 선행 커밋 `3105869` 위에 `b215465`를 fast-forward로 반영·push했다.
- 최종 `HEAD == origin/main == b215465`, ahead/behind `0/0`, 작업 트리 clean이다.
- 최신 전체 suite `744 passed`, main 코드 반영 후 집중 테스트 `74 passed`,
  RAG/Archive 문서 계약 테스트 `19 passed`, PowerShell 예제 4블록 구문 검사와 `git diff --check` 통과.
- 미니PC Archive pull·재시작·healthcheck는 오너 지시대로 나중 패치 단계까지 보류했다.

**RAG 미니PC 실측 (2026-07-27 00:14~00:19 KST)**
- 실제 스케줄 checkout은 `C:\projects\naver_cafe_archive_rag`이며
  `RAG-IncrementalIndex`는 enabled/`Ready`, 최근 실행 `2026-07-26 16:30:01`, 결과 `0`,
  다음 실행 `2026-07-27 16:30:00`이다.
- 실제 manifest/Qdrant는 함께 `2026-07-24 16:38` 갱신됐고 manifest unique 청크 `50,957`,
  최신 반영 article ID `173453`이다.
- Archive 최신 본문수집은 article ID `173480`, 작성시각 `2026-07-26 20:00:10`이다.
  공식 `--dry-run --no-telegram`은 rc=0, 현재 `50,966`/반영 `50,957`로 신규 `9청크`를 감지했다.
  이 글들은 7월 26일 16:30 태스크 실행 뒤 수집됐으므로 다음 일일 실행 대기분이다.
- RAG writer 프로세스는 0개였고, dry-run은 Archive DB·Qdrant·manifest·태스크·시크릿을 변경하지 않았다.
- 기존 사전점검 문서의 고정 예시 경로가 실제 스케줄 checkout과 달라, 태스크 `WorkingDirectory`를
  우선 권위로 사용하도록 문서를 갱신했다.

---

## 2026-07-27 · 노트북 · 브랜치 `agent/archive-session-closeout-20260727` (Archive 개발 PC 작업 종료 상태 확정)

**오늘 최종 상태**
- Enter-wait 통합·죽은 코드 제거 `3105869`와 stdin EOF fail-closed 보강 `b215465`가 원격 `main`에 반영됐다.
- 최신 검증 기준은 관련 테스트 `126 passed`, 전체 suite `743 passed`, compileall과 `git diff --check` 통과다.
- 개발 PC 기준 즉시 착수할 Archive 우선 작업은 없다. 다른 작업을 검토해 우선순위를 다시 정할 때까지
  Archive 코드는 `b215465` 기준으로 동결한다.

**남은 운영 작업**
- 미니PC는 아직 `b215465`를 pull하지 않았으며 CollectLoop 재시작·60초 healthcheck도 수행하지 않았다.
- 오너 지시대로 미니PC 패치는 나중에 별도 승인 범위로 진행한다.
- 완전 로그오프 사각지대는 구조 변경 후보이므로 별도 설계·승인 전 착수하지 않는다.

---

## 2026-07-27 · 노트북 · 브랜치 `agent/archive-console-enter-eof-hardening-20260727` (원격 통합 후 EOF 안전 종료 보강)

**한 일**
- 원격 `main`에 먼저 반영된 `3105869`의 Enter-wait 통합을 기준으로 재검토하고, 중복 구현을 병합하지 않았다.
- 공용 helper가 비Windows stdin EOF를 로그인 완료로 오인하던 동작을
  `ConsoleInputClosedError`로 fail-closed 처리했다.
- headed 수동 로그인과 상주 루프 준비 중 EOF는 traceback 대신 rc=2로 종료하며,
  브라우저 세션과 loop lock을 정리한다.
- 기존 프롬프트 인자, Windows `msvcrt`, interactive/noninteractive, API `code-0004` 권위는 유지했다.

**검증/승인**
- 관련 테스트 `126 passed`, 전체 suite `743 passed`, compileall과 `git diff --check` 통과.
- 2026-07-27 오너가 기능 브랜치 push·리뷰와 main 반영까지 승인했다.
- 미니PC pull·재시작·패치는 별도 지시까지 계속 보류한다.

---

## 2026-07-26 · 노트북 · 브랜치 `agent/archive-console-enter-wait-cleanup-20260726` (Enter 대기 통합·죽은 코드 제거)

**한 일**
- Windows 콘솔 Enter 대기를 `src/console_io.py`의 공용 helper로 통합하고
  `browser.py`, `daily_archive.py`, `index_tail.py`, `run_daily_archive_loop.py`의 중복 구현을 제거했다.
- headed 수동 로그인과 interactive/noninteractive 동작, Windows `msvcrt`, 프롬프트,
  비Windows stdin EOF 계약을 테스트로 고정했다.
- 호출자 검색과 전체 테스트를 거쳐 미사용 `daily_archive.fetch_list_rows`,
  `build_daily_archive_command` 및 전용 보조 코드·테스트를 제거했다.
- 기존 로그인 메시지, `member_api.check_member_login()`의 API `code-0004` 권위,
  `browser.py` HTML 로그인 휴리스틱은 유지했다.
- 실제 기본 DB에 암묵적으로 의존하던 `test_batch_recollect` 한 건을 가짜 연결로 격리했다.

**검증**
- 관련 테스트 `134 passed`, 전체 suite `738 passed`, compileall과 `git diff --check` 통과.
- RAG 소유 파일, trading-bot, 운영 DB/Qdrant, 미니PC는 접근·변경하지 않았다.

**배포/다음 작업**
- 오너 지시로 미니PC pull·재시작·라이브 healthcheck는 나중 패치 단계로 보류한다.
- 남은 Archive 운영 이슈는 완전 로그오프 사각지대이며 구조 변경이므로 별도 설계·승인 전 착수하지 않는다.

---

## 2026-07-26 · 노트북 · 브랜치 `agent/archive-notebook-pull-entry-20260726` (Git pull 기반 인수인계)

**한 일**
- 노트북 작업자가 별도 전달 프롬프트 없이 Git 문서만으로 인수인계받도록 이 대장 상단에 영구 시작점을 추가했다.
- Archive 전용 worktree의 clean 상태를 먼저 확인하고 `git pull --ff-only origin main`을 실행한 뒤
  `docs/ARCHIVE_NOTEBOOK_HANDOFF.md`를 읽는 단일 진입 절차로 정리했다.
- 일반 `git pull` 대신 fast-forward 전용으로 제한해 로컬 분기나 예상치 못한 merge가 있으면 안전하게 멈춘다.
- 정본의 pull 후 clean 검사와 `HEAD == origin/main` 게이트도 통과해야 개발을 시작할 수 있다.

**다음 작업**
- 정본 문서 §4에 따라 Enter-wait 중복과 죽은 코드 정리를 테스트 우선으로 진행한다.

---

## 2026-07-26 · 노트북 · 브랜치 `agent/archive-notebook-handoff-20260726` (노트북 개발 인수인계 정본)

**한 일**
- 노트북 작업자가 채팅 전문 없이 Git만으로 이어받도록 `docs/ARCHIVE_NOTEBOOK_HANDOFF.md`를 신설했다.
- Archive 전용 clean worktree `C:\tmp\naver_cafe_archive_archivefork`와 RAG 변경이 남은
  `C:\projects\naver_cafe_archive`를 구분하고, 후자에서 pull/reset/clean/stash/checkout을 금지했다.
- 첫 fetch·dirty 검사, 완료된 운영 상태, 다음 작업(Enter-wait 중복·죽은 코드), 소유권,
  전체 개발 사이클, 미니PC 공용 브리지 승인 게이트와 보고 형식을 한 문서에 고정했다.

**노트북 작업자의 지금 할 일**
1. `docs/ARCHIVE_NOTEBOOK_HANDOFF.md`를 처음부터 끝까지 읽는다.
2. Archive 전용 clean worktree에서 `git pull --ff-only origin main` 후 `origin/main`과 clean 상태를 재확인한다.
3. 새 브랜치/worktree에서 Enter-wait 중복·죽은 코드 정리를 테스트 우선으로 진행한다.

**주의**
- 기본 저장소의 RAG 변경 7개와 미추적 `scripts/_step3_verify_v2.py`를 보존한다.
- 미니PC pull·재시작·태스크 변경은 오너의 정확한 승인 전 금지한다.

---

## 2026-07-24 · 개발 PC · 브랜치 `agent/rag-ops-hardening-20260724` (RAG 운영 하드닝)

**상태**
- 최신 기준점: `origin/main` = `52def4d2cb3fa1947ee0b49907d38b3d3055ae71`.
- 오너가 검증 결과를 확인하고 작업 브랜치 커밋·푸시 진행을 승인했다.
- 이 변경은 작업 브랜치에만 반영하며 미니PC 코드, 작업 스케줄, 데이터, 시크릿은 변경하지 않는다.

**변경 내용**
1. `scripts/register_rag_index_schedule.ps1`
   - SSH 접속 시 `$env:USERDOMAIN`이 `WORKGROUP`으로 잡혀 Task Scheduler 계정 SID 해석이 실패하는 문제를 수정했다.
   - `WindowsIdentity.GetCurrent().Name`으로 현재 인증 토큰의 정규 계정명(`MACHINE\user` 또는 `DOMAIN\user`)을 사용한다.
   - 계정명이 비었거나 qualified 형식이 아니면 작업 등록 전에 중단하는 fail-closed 동작을 추가했다.
2. `scripts/run_rag_incremental_notify.py`
   - 마지막 수집글 생존신호 조회를 `saved_at DESC`에서 `article_id DESC`로 변경했다.
   - `article_id`는 Naver의 단조 증가 글 번호이자 Archive DB의 `INTEGER PRIMARY KEY`이므로 forward 수집 경계를 나타낸다.
   - 과거 글 재수집/백필에 따른 `saved_at` 왜곡과 16GB 테이블 전체 정렬을 제거했다.
   - Archive DB는 계속 SQLite `mode=ro`로만 읽고, RAG 쪽에서 인덱스나 데이터를 쓰지 않는다.
3. 회귀 테스트와 `docs/DEPLOY_MINIPC.md`를 위 계약에 맞게 갱신했다.

**실측 검증**
- 표적 테스트: `40 passed`, rc=0.
- RAG 관련 통합 테스트: `469 passed in 11.81s`, rc=0.
- HANDOFF 갱신 후 문서 계약 테스트: `14 passed in 0.05s`, rc=0.
- 최신 `origin/main` 재배치 후 RAG·문서 표적 테스트: `54 passed in 0.63s`, rc=0.
- 최신 기준 전체 suite: `732 passed, 1 failed in 16.37s`, rc=1. 실패는
  `tests/test_batch_recollect.py::test_batch_login_check_uses_article_list_page_one`의
  `sqlite3.OperationalError: no such table: articles`이며, 깨끗한 `origin/main`에서도 동일 테스트가
  `1 failed in 0.20s`, rc=1로 재현되어 이번 RAG 변경과 무관한 기준선/환경 문제임을 확인했다.
- PowerShell AST: `powershell_parse_errors=0`.
- `git diff --check`: rc=0 (CRLF 변환 경고만 있음).
- 미니PC read-only 실DB 조회: 최신 `article_id=173413`, 작성일 `2026-07-23 22:07:42`,
  `elapsed_ms=1.717`, `query_only=1`, rc=0. `article_id`는 `INTEGER PRIMARY KEY`이고 별도 인덱스는 없다.
- 미니PC read-only 계정 확인: 환경값은 `USERDOMAIN=WORKGROUP`이지만 인증 토큰 해석값은
  `DESKTOP-NFN1RCA\미니PC`; 동일 계정으로 `S4U / Limited` principal 생성 성공, rc=0.
- 독립 코드 리뷰: PASS, P0-P2 없음.
- 독립 운영 리뷰: PASS, P0-P3 없음.

**다음 단계**
1. 작업 브랜치를 커밋·푸시한 뒤 정식 절차로 병합한다.
2. 배포 승인을 별도로 확인한 뒤 미니PC의 깨끗한 RAG checkout만 승인 커밋으로 갱신한다.
3. 자산 안전 게이트 PASS를 재확인하고 스케줄을 재등록한다.
4. `Start-ScheduledTask` 실제 실행, `LastTaskResult=0`, 텔레그램 수신을 확인한다.
5. 마지막 글 날짜 정체만으로 Archive 수집 사망을 단정하지 말고 Archive healthcheck와 일일요약을 함께 확인한다.

---

## 2026-07-24 · 개발 PC · 브랜치 `agent/archive-estimate-recalibration-20260724` (URL별 tail estimate 보정)

**한 일**
- 수동 `index_tail.py`의 미지정 `--estimate`를 URL별로 계산한다. 멤버 REST API는 기존
  `2828×15건`을 API 20건/페이지로 올림 환산한 `2121`, 기존 HTML fallback은 `2828`을 유지한다.
- 사용자가 `--estimate`를 명시하면 URL 종류와 관계없이 그 값을 우선한다.
- estimate부터 전진 15페이지가 모두 유효할 때 마지막 확인 페이지를 실제 tail로 오판하던 동작을 제거하고,
  빈 페이지 경계를 확인하지 못했으므로 `None`으로 안전 실패하게 했다.
- 운영 문서의 잘못된 `batch_recollect --estimate` 표기를 실제 소유자인 `index_tail.py` 기준으로 정정하고
  완료된 보류 항목을 제거했다.

**검증/리뷰**
- REST 2121/HTML 2828/custom 우선, CLI 도움말, 전진 한계 안전 실패 회귀 테스트를 추가했다.
- 관련 테스트 35개, 전체 suite 731개 통과, py_compile·`git diff --check` 통과.
- 독립 리뷰에서 전역 2121이 HTML fallback을 깨뜨리는 P2를 발견해 URL별 기본값으로 수정했다.
  재리뷰 최종 P0~P3 없음 승인.

**미니PC 배포·라이브 검증 (2026-07-24 09:53 KST)**
- 미니PC 로컬 HANDOFF 커밋 `91dc050` 때문에 원격과 분기된 상태를 발견해 즉시 ff-only 배포를 중단했다.
  그 26줄 기록을 이 대장에 보존하고, 미니PC에는
  `backup/archive-minipc-handoff-91dc050-20260724` ref로 원본 커밋을 보존했다.
- tracked clean과 보호 파일 해시를 확인한 뒤 미니PC `main`을 당시 `origin/main=52def4d`로 안전 재정렬하고
  CollectLoop를 정본 절차로 재시작했다. 최종 HEAD와 로컬 `origin/main`은 `52def4d`로 일치했다.
- 최종 60초 healthcheck `HEALTHY`, rc=0, controller instance 1개, latest article id=173441,
  세션 경고 없음. CollectLoop `Running`, Watchdog/DailySummary `Ready`. 최종 결론 `LIVE VERIFIED`.

**다음 작업**
- Enter-wait 중복·죽은 코드 정리. 완전 로그오프 사각지대 개선은 운영 구조 변경이라 후순위다.

---

## 2026-07-23 · 미니PC · 로컬 커밋 `91dc050` (Archive 노트북 인수인계 기록 보존)

> 이 항목은 미니PC가 `34cb669` 위에 로컬로 작성한 `docs: complete Archive laptop handoff`의
> 내용을 원격 대장에 보존한 것이다. 원본 커밋은 미니PC에서 백업 ref 생성 전까지 삭제하지 않는다.

**당시 권위 상태**
- Archive 수동 snapshot/tail 일시 오류 재시도 변경은 `6e07916`에 반영됐고, 라이브 검증 기록은
  후속 문서 커밋 `34cb669`에 반영됐다.
- `scripts/index_tail.py`의 실제 diff를 재검토했다. 변경은 수동 `_create_snapshot`/`find_tail`의
  동일 페이지 재시도와 재시도 소진 시 fail-closed 반환에 한정되며 무인 realtime 경로는 그대로였다.
- 미니PC 배포는 완료 상태였다. 배포 전·후 healthcheck `HEALTHY`/rc=0, controller instance 1개,
  최종 `LIVE VERIFIED`였으므로 당시 추가 배포·재시작은 필요하지 않았다.

**당시 인수인계 검증**
- index-tail 표적 테스트 4파일: `23 passed in 2.78s`.
- Archive 미니PC 문서 계약 테스트: `6 passed in 0.07s`.
- `scripts/index_tail.py`와 신규 회귀 테스트 AST parse PASS, `6e07916^..6e07916` `git diff --check` PASS.
- 운영 DB·수집·서비스·스케줄·시크릿은 조회·변경·재시작하지 않았다. RAG·Trading 저장소에도 접근하지 않았다.
- 기존 미추적 `scripts/_step3_verify_v2.py`는 SHA-256
  `56CBA94517054572A8148F3A9EAB6218628884AC1103DF2F88488CF85719A2EA` 그대로 보존했다.

**당시 노트북 인계 지시**
1. 저장소 `main`에서 ff-only로 최신 HANDOFF를 받는다.
2. `git status --short --branch`와 `git log -1 --oneline`으로 clean tracked 상태를 확인한다.
3. 다음 후보는 Enter-wait 중복·죽은 코드 정리 또는 `--estimate` 재보정이었다.

---

## 2026-07-23 · 개발 PC · 브랜치 `agent/archive-manual-scan-retry-20260723` (수동 tail 탐색 일시 오류 개선)

**한 일**
- 수동 양산 모드의 `_create_snapshot`/`find_tail`에 전용 일시 오류 재시도를 추가했다.
- 소켓·5xx 등은 같은 페이지를 최초 시도 후 최대 3회 재시도하고, `is_block_error()`가 분류하는
  code-0004·권한·CAPTCHA 등은 대기 없이 즉시 중단한다.
- tail 전진 오류에서 마지막 성공 페이지를 tail로 오판하거나, 후퇴 오류 페이지를 건너뛰는 동작을 제거했다.
  재시도 소진 시 `None`으로 실패해 부정확한 양산 범위를 만들지 않는다.
- 수동 전용 `MANUAL_SCAN_MAX_RETRIES`를 두어 무인 realtime의 기존 `MAX_TRANSIENT_FAILS` 계약과 분리했다.

**검증/리뷰**
- 신규 경계 테스트 7개: 3회 재시도 후 성공, 4번째 실패에서 소진, 차단 무재시도,
  전진·후퇴 오판 방지, realtime helper 비사용을 고정했다.
- 관련 테스트 31개, 당시 전체 suite 727개 통과. 독립 리뷰에서 실제 재시도 횟수 off-by-one P2를 발견해
  최초 1회+재시도 3회로 수정했고, 재리뷰 최종 P0~P3 없음 승인.

**미니PC 라이브 검증 (2026-07-23 09:52 KST)**
- `main`을 `64e4724 → 6e07916`으로 ff-only 갱신. 배포 전·후 healthcheck 모두 `HEALTHY`, rc=0.
- CollectLoop 재시작 전·후 `Running`, controller instance 1개, 새 loop lock 정상, 세션 경고 없음.
- Archive Python 2개와 Archive Chrome 5개만 정리했고 비Archive Python 종료는 0개다.
- Watchdog은 enabled/`Ready`, DailySummary는 `Ready`, latest article id=173371.
- 알려진 미추적 `scripts/_step3_verify_v2.py`는 SHA-256 전후 동일하게 보존됐다. 최종 결론 `LIVE VERIFIED`.

**다음 작업**
- Enter-wait 중복·죽은 코드 정리 또는 `--estimate` 페이지당 건수 재보정을 별도 브랜치에서 진행한다.

---

## 2026-07-23 · 개발 PC + 미니PC · 브랜치 `agent/archive-watchdog-self-filter-20260723` (Archive 라이브 배포 완료)

**한 일**
- 미니PC `main`을 ff-only로 `6b2f064 → b5c939a` 갱신하고 `d8c806c` index-tail 단일 정본을 운영에 반영했다.
- 첫 재시작은 배포 문서의 워치독 잔류 검사기가 maintenance PowerShell 자기 자신을
  `archive_watchdog.ps1`로 오인해 안전 중단했다. 현재 `$PID`만 제외하도록 수정하고 실제 워치독 탐지는 유지했다.
- 수정은 PowerShell 5 모의 필터(실제 watchdog PID만 탐지), 5개 블록 구문 검사, 계약 테스트 6개,
  전체 suite 720개 통과 후 독립 리뷰 P0~P3 없음으로 승인됐다.

**미니PC 라이브 검증 (2026-07-23 09:28 KST)**
- 배포 전·후 healthcheck 모두 `HEALTHY`, rc=0. 최종 HEAD와 `origin/main`은
  `b5c939a6c9d2f455221210ad0a22991340be3a2f`로 일치한다.
- `Archive-CollectLoop=Running`, controller instance 1개, 새 loop lock 정상, 세션 경고 없음.
- Archive Python 2개와 Archive Chrome 5개만 정리했고 비Archive Python 종료는 0개다.
- Watchdog은 enabled/`Ready`, DailySummary는 `Ready`. 최근 cycle rc=0, saved delta=3, latest article id=173369.
- 알려진 미추적 `scripts/_step3_verify_v2.py`는 SHA-256 전후 동일하게 보존됐다.

**다음 작업**
- `find_tail`/`_create_snapshot`의 일시 오류 분류 개선(수동 양산 모드만 해당)을 별도 브랜치에서 진행한다.

---

## 2026-07-22 · 개발 PC · 브랜치 `agent/archive-minipc-handoff-20260722` (pull 기반 Archive 인수인계)

**한 일**
- 별도 txt/채팅 복붙 없이 미니PC 담당자가 Git만으로 이어받도록
  `docs/ARCHIVE_MINIPC_HANDOFF.md`를 **현재 Archive 작업 정본**으로 신설했다.
- 담당자는 `git fetch` → tracked dirty 확인 → `main` ff-only → `d8c806c` 포함 검증 → 배포 전 healthcheck →
  Archive PID만 보호적으로 정리해 CollectLoop 재시작 → 배포 후 healthcheck 순서로 실행한다.
- RAG Python 보호, 미추적 `_step3_verify_v2.py` 보존, 실패 시 반복 재시작 금지와 보고 형식을 문서에 고정했다.

**미니PC 담당자의 지금 할 일**
- `git fetch origin` 후 `docs/ARCHIVE_MINIPC_HANDOFF.md`만 순서대로 실행한다. 문서의 dirty 검사 전 pull 금지.
- 성공 기준은 배포 후 `HEALTHY`, 종료코드 0, controller 1개, `LIVE VERIFIED` 보고다.

**다음 작업**
- 라이브 검증 성공 후 `find_tail`/`_create_snapshot` 일시 오류 분류 개선을 별도 세션에서 진행.

---

## 2026-07-22 · 개발 PC · 브랜치 `agent/rag-minipc-handoff-20260722` (복붙 없는 RAG 인수인계 정리)

**한 일**
- RAG 담당자가 채팅 프롬프트를 복사하지 않고 `git fetch` 후 바로 이어받도록
  `docs/RAG_MINIPC_PREFLIGHT.md`를 인수인계·배포 전 사전점검 정본으로 신설했다.
- `docs/DEPLOY_MINIPC.md`와 `MACHINE_SYNC.md`의 시작점이 새 정본을 가리키도록 정리했다.
- 새 정본은 Git/worktree/스케줄/자산/.env 키 존재 여부를 읽기 전용으로 실측하고, dirty 상태에서는
  pull/reset/clean/stash 없이 중단·보고하도록 고정한다.

**현재 권위 상태**
- 이 작업의 기준점은 `d8c806c`이며, 본 인수인계 변경은 그 위에 이어진다. 수신자는 고정 해시를 최신값으로
  가정하지 말고 `git fetch origin` 후 실측한 `origin/main`을 권위값으로 사용한다.
- 기준점에는 Archive index-tail 통합과 직전 `082a24c`의 fail-closed RAG 배포 자산 안전 게이트가 포함된다.
- 실제 미니PC RAG 배포와 `RAG-IncrementalIndex` 등록은 미수행.
- 개발 PC 기본 worktree `C:\projects\naver_cafe_archive`는 로컬 main이 원격보다 뒤처져 있고, 원격과 내용이 같은
  7개 파일이 modified로 표시되며 미추적 `scripts/_step3_verify_v2.py`가 있다. 별도 정리 전 건드리지 않는다.
- 깨끗한 RAG worktree는 `C:\projects\rag_predeploy_guard_20260722`이다.

**검증**
- 신규 정본의 PowerShell 예제 4블록 구문 검사: `powershell_parse_errors=0`, rc=0.
- 인수인계·기존 운영문서·focused runner 관련 테스트: `34 passed in 0.13s`, rc=0.
- `scripts/run_rag_focused_tests.py`: 신규 문서 계약 테스트 5개를 포함해 전체 PASS, rc=0.
- `git diff --check` 통과. 실제 배포·DB/Qdrant/.env/스케줄러 쓰기 없음.

**다음 작업**
- 미니PC RAG 담당자는 `docs/RAG_MINIPC_PREFLIGHT.md`만 따라 읽기 전용 실측 보고를 제출하고 대기한다.
- PM이 보고를 확인해 배포 commit/tag와 실제 배포를 별도로 승인하기 전까지 pull, 데이터 이관, `.env` 변경,
  스케줄 등록·실행을 금지한다.
- 검색 API·Phase 2 잔여 배치·대규모 리팩토링은 계속 보류한다.

---

## 2026-07-22 · 개발 PC · 브랜치 `agent/archive-index-tail-unify-20260722` (Archive 포크 통합)

**한 일**
- 556줄 이상 중복되던 `scripts/index_tail.py`/`scripts/index_tail_realtime.py` 포크를 통합.
  `index_tail.py`가 수동 양산·collect-after-snapshot·`run_realtime_index`의 단일 정본이다.
- `index_tail_realtime.py`는 기존 스크립트 경로와 import 계약을 보존하는 20여 줄 호환 shim으로 축소.
  top-level import/직접 파일 실행뿐 아니라 package import/`python -m`도 지원하며, import 시 정본과 동일한
  모듈 객체를 반환해 기존 monkeypatch/private helper 계약을 유지한다.
- 무인 상주 루프는 `run_realtime_index`를 호환 shim이 아니라 `index_tail` 정본에서 직접 import한다.
- `tests/test_index_tail_shared_module.py` 신설: 동일 모듈 객체, shim 내 함수/클래스 재분기 금지,
  무인 루프 정본 import, 두 CLI 옵션 계약, package import/모듈 실행을 고정.
- 운영 러너북 §6의 양쪽 동시 수정 규칙을 단일 정본 규칙으로 교체하고 포크 중복을 잔여 이슈에서 제거.

**검증/리뷰**
- 관련 테스트 **86 passed**. 격리 worktree는 실제 16GB DB 대신 `src.db.init_db()`로 최소 테스트 스키마를
  만든 뒤 전체 suite **709 passed**를 검증했다.
- 독립 리뷰에서 package import/`python -m scripts.index_tail_realtime` 실패 P2를 발견해 dual-context
  import와 회귀 테스트를 추가. 재리뷰 최종 P0~P3 없음 승인, `git diff --check` 통과.
- 작업 기준점 `origin/main 082a24c`. 기본 체크아웃의 RAG 미커밋 변경을 보호하기 위해
  `C:\tmp\naver_cafe_archive_archivefork` 별도 worktree에서 작업.

**배포 시 필수**
- 무인 루프의 실제 import 대상이 바뀌는 운영 코드다. main 반영 후 미니PC에서 CollectLoop를 안전 재시작하고
  healthcheck `--observe-seconds 60`으로 `HEALTHY` 및 단일 controller/DB 활동을 라이브 확인한다.

**다음 작업**
- `find_tail`/`_create_snapshot`의 일시 오류 분류 개선(수동 양산 모드만 해당).
- Enter-wait 중복·죽은 코드 정리는 후순위.

---

## 2026-07-22 · 개발 PC · 브랜치 `agent/rag-predeploy-guard-20260722` (RAG 배포 안전 게이트)

**한 일 (코드·문서 변경 — 독립 재리뷰 PASS, 오너 승인으로 반영 절차 수행)**
- 신규 읽기 전용 검사기 `scripts/check_rag_deploy_assets.py`: Qdrant `meta.json` + collection SQLite를
  `mode=ro/query_only`로 검사하고, points 수와 manifest(우선) 또는 seed unique IDs 수가 같을 때만 PASS.
  collection=`goodmorning_chunks`, vector=1024, distance=Cosine, archive.db read-only 접근도 함께 검증.
- `run_rag_incremental_notify.py`가 매 실행 전 위 안전 게이트를 호출하도록 연결. 실패 시 색인기를 시작하지 않고
  rc=1. `--manifest-path`/`--seed-ids-path` 전달 지원. dry-run 문구를 `신규 N청크 감지 (미반영)`으로 수정.
- `register_rag_index_schedule.ps1`도 등록 전에 안전 게이트를 실행하고 실패 시 태스크 등록/덮어쓰기를 차단.
- 배포·증분색인 문서와 focused runner/테스트 갱신. Archive DB/Qdrant/.env/스케줄러 쓰기 없음.

**실측 검증**
- 최신 개발 자산: Qdrant points=50,583 / manifest rows=unique=50,583 / 1024-Cosine → `status=PASS`,
  deterministic UUID5 point ID 집합 완전 일치(`point_ids_match_baseline=true`), `write_performed=false`;
  wrapper dry-run rc=0, `현재 50,645 / 반영 50,583 / 신규 62 감지(미반영)`.
- 의도적 구형 seed 조합: points=50,583 vs seed unique=50,131 → 안전 게이트 `status=FAIL`, wrapper rc=1,
  색인기 미실행.
- 안전 게이트+래퍼 타깃 테스트: `38 passed`; RAG focused runner: PASS(rc=0).
- 데이터가 있는 공유 작업트리에서 당시 전체 suite `687 passed in 27.56s`(동시 Archive 세션 신규 테스트 포함).
  분리 worktree 전체 suite는 로컬 `data/archive.db` 부재로 Archive 테스트 1건이
  `sqlite3.OperationalError: no such table: articles`로 실패하고 최종 `685 passed`; RAG 변경 관련 실패 아님.
- PowerShell parse OK, `git diff --check` OK, Python 3.12.10.

**독립 리뷰 반영**
- 1차 리뷰 FAIL: 동일 개수·다른 ID 집합이 PASS하는 P1, 비문자/비계약 chunk_id 허용 P2,
  child rc=0인데 summary가 없거나 불완전해도 성공 처리하는 P2 확인.
- 수정: Qdrant SQLite stored ID를 pickle 실행 없이 안전 파싱 → `rag_qdrant.chunk_id_to_point_id()`의 UUID5
  집합과 완전 비교, chunk_id 계약(`<article_id>:<chunk_index>`) 검증, rc=0 summary 필수 필드·모드 검증.
- 동일 개수·다른 ID / 손상 chunk_id / 불완전 성공 summary 회귀 테스트 추가.
- 2차 독립 재리뷰: 코드 정확성 리뷰 PASS + 운영/보안 리뷰 PASS. 추가 P0~P3 없음, 승인 가능.
  잔여 리스크는 고정된 qdrant-client 로컬 저장 포맷이 향후 바뀌면 fail-closed로 중단될 수 있다는 호환성뿐.

**작업 격리/주의**
- 동시 Archive 세션이 기본 작업트리를 `agent/archive-healthcheck-20260722`로 전환해,
  RAG 변경은 `C:\projects\rag_predeploy_guard_20260722` 별도 worktree로 분리했다.
- 기존 미추적 `scripts/_step3_verify_v2.py`는 수정·복사·삭제·스테이징하지 않았다.

**다음 작업**
- 독립 리뷰 승인 기준을 충족해 작업 브랜치에 반영. `main` 병합과 실제 미니PC 배포는 PM 승인 전 금지.
- PM이 실제 미니PC 배포를 승인하면 최신 Qdrant+manifest 한 쌍 이관 → 안전 게이트 PASS → dry-run →
  스케줄 등록 순서. 검색 API·Phase 2 잔여 배치·대규모 리팩토링은 계속 보류.

---

## 2026-07-22 · PC · 브랜치 `agent/archive-healthcheck-20260722` (Archive 통합 상태 점검기)

**한 일**
- `scripts/archive_healthcheck.py` 신설 — Git, 16GB DB의 `MAX(article_id)`, DB/WAL 시각, 루프 상태·락,
  세션만료 상태, 최근 원본 사이클, Windows 태스크 3종, Archive 프로세스를 한 번에 **논리적 읽기 전용** 진단
  (라이브 WAL 조회 시 SQLite가 기존 `-shm`을 갱신할 수 있음).
- 판정/종료코드: `HEALTHY=0`, `DEGRADED=1`, `STOPPED=2`; 자동화용 `--json`, 개발환경용
  `--skip-system`, 활동 재측정용 `--observe-seconds` 지원. 원본 로그·프로세스 명령줄은 출력하지 않고 상태
  문자열의 쿠키·텔레그램·Authorization 값도 레닥션.
- 16GB DB 보호를 테스트로 고정: `COUNT(*)`/`saved_at` 조회 금지, read-only URI + `query_only` +
  `MAX(article_id)`만 허용. 최근 3개 로그/시간대별 신선도와 Python 부모-자식 관계 기반 중복 수집기 판정 포함.
- `docs/ARCHIVE_MINIPC_OPERATIONS.md` §4에 실행법·종료코드·안전 경계 추가.

**검증/관찰**
- `PYTHONUTF8=1 .venv\Scripts\python.exe -m pytest -q` 전체 **685 passed**, healthcheck 전용 **18 passed**.
  독립 리뷰 2회에서 stale-liveness·중복 수집기·장외 로그·WAL 문서 문제를 수정했고 최종 P1/P2 없음 승인.
- 이 PC(`DESKTOP-UQSM459`) 실실행은 `STOPPED`: Archive 태스크 3종/프로세스 없음, DB max id 172569,
  상태·최근 사이클은 07-04 실패에서 정지. 운영 미니PC가 아닌 개발 PC라는 기존 판단과 일치.
- 작업 도중 별도 RAG 변경이 같은 워킹트리에 나타남. RAG 소유 파일은 수정하지 않았고 Archive 파일만
  명시적으로 다룬다. 기존 `scripts/_step3_verify_v2.py`도 그대로 보존.

**다음 작업**
- 오너 확인 후 Archive 파일만 명시적으로 커밋·푸시하고 main에 ff-only 반영.
- 실제 운영 미니PC에서 `archive_healthcheck.py`를 실행해 `HEALTHY` 기준선과 태스크 출력 실증.

---

## 2026-07-20 · 미니PC · RAG 운영 세션 (오너 지시로 이 항목만 추가 — 코드 무변경·커밋 없음)

**전체 상태 스냅샷 (2026-07-20 15:27 실측 — 인수인계 기준점)**
- `main` = `origin/main` = `7d01def` (0/0 동기화). 배포 기준점 태그 `deploy-baseline-20260705` = `c8892a3`(512 테스트 통과 시점).
- **Archive봇(수집): 무인화 완료·가동 중.** 스케줄 태스크 `Archive-CollectLoop`(Running) / `Archive-DailySummary`(매일 20:00 요약) / `Archive-Watchdog`(매시 생존확인·자동재시작). `archive.db` 16GB, WAL이 분 단위로 갱신 중(수집 살아있음 실측). 07-05 핸드오프의 "무인 수집 미구현" 병목은 **해소됨** (`bd06136`~`7d01def`: REST 수집 병합→부팅 런처→HEADLESS→세션만료 알림→루프 내성→시크릿 스크럽→워치독).
- **RAG봇(색인): 미배포·PM 지시 대기.** `RAG-IncrementalIndex` 태스크 미등록 상태 확인. 코드·러너는 main에 완성돼 있음.
- **trading-bot: 별도 repo, 이 대장 범위 밖** (모의투자 forward 2026-07-06 시작, 안정 관찰 중).

**한 일 (07-06~07-20, 미니PC RAG 운영 담당 — 전부 읽기 전용 + worktree 1개 생성)**
- PM 승인 하에 **RAG 배포 사전점검** 수행: `C:\projects\naver_cafe_archive_rag`에 git worktree(detached @ `c8892a3`) 생성. 본 리포·Archive봇 작업물 무변경.
- 사전점검 결과: Python 3.12.10 OK / requirements·.env.example·스크립트 4종(register_rag_index_schedule.ps1, run_rag_incremental_notify.py, notify_telegram.py, update_rag_index_incremental.py) 존재 OK. **배포일에만 할 것**: `.env` 3값(VOYAGE_API_KEY, RAG_TELEGRAM_BOT_TOKEN, RAG_TELEGRAM_CHAT_ID) 입력 + `data/qdrant/`(≈600MB)·`data/rag_index_manifest.jsonl`(또는 embeddings_phase2_ids.npy) 수동 이관(누락 시 5만 청크 재임베딩 대량 과금) + 스케줄 등록(`-DbPath "C:\projects\naver_cafe_archive\data\archive.db"`).
- Archive봇 수집 생존 실측 확인(파일시각·WAL 기준). 수집 死 아님.

**⚠️ 주의 (인수인계 필독)**
- `scripts/_step3_verify_v2.py` — **미추적 WIP** (RAG 평가용 합성쿼리 v1 vs v2 비교·자가검증 스크립트). 원 작성 세션/담당 미확인. **git clean 등으로 지우지 말 것.** 소유 확인 후 브랜치로 편입하거나 이관할 것.
- 이 항목은 미니PC에서 작성됨(오너 지시에 따른 문서 갱신). **커밋/푸시는 오너 승인 필요.** 미커밋 상태가 길어지면 미니PC `git pull`과 충돌 가능 → 빠른 승인·처리 요망.

**다음 작업**
- 미니PC RAG 색인 배포: **PM 지시 대기** (trading-bot 안정 확인 후). 배포 기준점을 태그 `c8892a3`로 갈지 당시 최신 main으로 갈지 **PM 미결** — 배포 지시 때 확정 필요.
- 배포 후 일상 운영: 매일 텔레그램 통지 확인(✅/🔴 + "마지막 수집글 작성일" 생존신호), `Get-ScheduledTaskInfo -TaskName RAG-IncrementalIndex`.
- 리포 공유 정리(미니PC 한 체크아웃을 Archive봇·RAG봇이 공유 중): 전 봇 안정화 후 별도 세션에서 논의(PM 방침).
- 검색 API·Phase 2 잔여 배치·대규모 리팩토링: 계속 보류(PM 지시 시 착수).

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
