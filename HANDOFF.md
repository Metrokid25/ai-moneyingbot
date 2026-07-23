# 인수인계 대장 (PC ↔ 노트북)

> 작업 세션이 끝날 때 **맨 위에 새 항목**을 추가한다(최신이 위). 다른 기계에서 이어받는 Claude/사람이
> 이 파일만 읽으면 "직전에 뭘 했고, 산출물이 어디 있고, 다음에 뭘 할지"를 안다.
> - 규칙: 데이터/정책 = MACHINE_SYNC.md, 세션별 진행 = 이 파일, 결과물 상세 = `docs/*.md`.
> - 이 파일과 `docs/`는 git-tracked → commit+push 해야 다른 기계가 본다. (`data/`의 mentor.db·qdrant는 수동 이관)

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

**배포 상태/다음 작업**
- 수동 양산 코드 변경이다. main 반영 후 미니PC ff-only 갱신과 운영 코드 라이브 검증이 필요하다.
- 다음 후보는 Enter-wait 중복·죽은 코드 정리. 완전 로그오프 사각지대 개선은 운영 구조 변경이라 후순위다.

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
