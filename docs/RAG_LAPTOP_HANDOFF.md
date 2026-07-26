# RAG 노트북 작업자 인수인계 정본

> 기준 시각: 2026-07-26 KST
>
> 대상 기계: `DESKTOP-UQSM459`
>
> 저장소: `https://github.com/Metrokid25/ai-moneyingbot`

이 문서는 노트북의 새 RAG 작업자가 채팅 기록이나 복사한 프롬프트 없이 Git 상태를 실측한 뒤
안전하게 이어받기 위한 단일 시작점이다. 작업자는 이 파일을 처음부터 끝까지 읽고 아래 순서대로
수행한다. 충돌 시 `docs/OWNERSHIP.md`와 `HANDOFF.md` 최신 항목이 우선한다.

## 1. 작업자가 바로 수행할 착수 절차

역할은 ai-moneyingbot의 노트북 RAG 담당자다. 오너는 방향과 승인만 결정한다.

작업을 시작하기 전에 반드시 아래 순서로 실측하고, 결과를 먼저 보고하라.

1. 작업 위치를 C:\projects\ai_moneyingbot_laptop_sync 로 고정한다.
2. git fetch origin 을 실행한다.
3. git status --short --branch, git rev-parse HEAD, git rev-parse origin/main,
   git rev-list --left-right --count HEAD...origin/main 을 실행한다.
4. HANDOFF.md 최상단, docs/RAG_LAPTOP_HANDOFF.md 전체,
   docs/OWNERSHIP.md 전체, MACHINE_SYNC.md를 읽는다.
5. origin/main과 origin/agent/rag-ops-hardening-20260724의 상태를 확인한다.

2026-07-26 인수인계 기준:
- 노트북 clean 기준 경로:
  C:\projects\ai_moneyingbot_laptop_sync
- 이 경로의 브랜치:
  agent/rag-laptop-sync-20260726
- 인수인계 브랜치 기준점 = origin/main =
  dc5c25241bd7127ab9fcacec6c8c5fd137ec6c38
- 정상적으로 pull한 뒤에는 tracked modified/untracked가 없어야 한다. 다른 변경이 보이면
  pull/reset/stash/clean을 실행하지 말고 파일 목록부터 오너에게 보고한다.
- RAG 운영 하드닝 브랜치:
  origin/agent/rag-ops-hardening-20260724
- RAG 운영 하드닝 커밋:
  3821e234ab1ff904e12d799f81cc3dc826b72527
- 위 하드닝은 독립 코드/운영 리뷰 PASS, 원격 푸시 완료 상태지만
  2026-07-26 기준 origin/main에는 아직 병합되지 않았다.

절대 건드리지 말아야 할 경로:
- C:\projects\naver_cafe_archive
  이 checkout은 main이 origin/main보다 13커밋 뒤이며 추적 수정 7개가 있다.
  scripts/_step3_verify_v2.py도 미추적 보호 대상이다.
  이 경로에서 pull, reset, checkout, clean, stash, 파일 삭제를 하지 마라.
- C:\projects\ai_moneyingbot_rag_agent
  agent/rag-ingest-boundary 전용 worktree다. 별도 지시 없이 수정하거나 병합하지 마라.

소유권:
- Archive봇만 archive.db/mentor.db에 쓴다.
- RAG봇은 archive.db를 읽기 전용으로만 사용하고 자기 Qdrant만 소유한다.
- trading-bot 데이터는 읽거나 쓰지 않는다.
- 연동 키는 article_id이며 API/JSONL 경계만 사용한다.

Git/운영 규칙:
- main 직접 커밋 금지. 새 변경은 agent/rag-* 브랜치에서만 한다.
- 커밋, 푸시, 병합은 오너 승인 후에만 한다.
- force push 금지.
- 미니PC는 운영 전용이다. 코드 수정 금지이며 승인된 commit/tag로 git pull만 한다.
- .env, 토큰, API 키를 출력하거나 Git에 넣지 않는다.
- 테스트 결과와 개수는 실제 출력만 보고한다. Python 실행 시 PYTHONUTF8=1을 사용한다.
- 미니PC 배포, 스케줄 재등록, 자산 이관, 실제 증분색인은 별도 명시 승인 전 금지한다.

현재 우선 작업:
1. RAG 하드닝 브랜치가 origin/main에 병합됐는지 읽기 전용으로 확인한다.
2. 미병합이면 origin/main...origin/agent/rag-ops-hardening-20260724의
   커밋과 변경 파일, PR 존재 여부를 보고한다.
3. 병합 또는 배포를 임의 실행하지 말고 오너 지시를 기다린다.
4. 새 개발 지시를 받으면 최신 origin/main에서 별도 agent/rag-* 브랜치를 만들고,
   구현 전 기존 코드와 테스트에 같은 기능이 없는지 먼저 검색한다.

착수 보고 형식:
- 기계명/작업 경로
- branch/HEAD/origin-main/ahead-behind
- tracked modified/untracked
- RAG 하드닝 브랜치의 병합 여부
- 읽은 정본 문서
- 실행하거나 변경하지 않은 항목
- 다음 권고 작업 1개

검증 출력이 오면 추측하지 말고 액면 그대로 먼저 읽어라.

## 2. 2026-07-26 실측 상태

### 안전한 노트북 기준 checkout

- 경로: `C:\projects\ai_moneyingbot_laptop_sync`
- 브랜치: `agent/rag-laptop-sync-20260726`
- 인수인계 브랜치 기준점: `origin/main@dc5c25241bd7127ab9fcacec6c8c5fd137ec6c38`
- upstream: `origin/agent/rag-laptop-sync-20260726`
- `git pull --ff-only`: `Already up to date`, rc=0
- 동기화 직후 tracked modified/untracked: 없음

이 브랜치는 노트북의 안전한 시작점이다. 새 기능을 구현할 때는 여기서 다시 별도
`agent/rag-*` 작업 브랜치를 만든다.

### 미병합 RAG 운영 하드닝

- 로컬 worktree: `C:\projects\rag_ops_hardening_20260724`
- 브랜치: `agent/rag-ops-hardening-20260724`
- 원격 커밋: `3821e234ab1ff904e12d799f81cc3dc826b72527`
- 상태: clean, 원격 푸시 완료
- 2026-07-26 `origin/main=dc5c252`에는 미병합
- 주요 변경:
  - SSH에서 `USERDOMAIN=WORKGROUP`으로 잡히는 문제를
    `WindowsIdentity.GetCurrent().Name` 기반 계정 해석으로 수정
  - 마지막 수집글 생존신호를 `saved_at DESC` 전체 정렬에서
    `article_id DESC` 기본키 탐색으로 변경
  - 테스트와 `docs/DEPLOY_MINIPC.md` 갱신
- 검증:
  - 독립 코드 리뷰 PASS
  - 독립 운영 리뷰 PASS
  - 최신 기준 RAG·문서 표적 테스트 `54 passed`
  - 전체 suite는 `732 passed, 1 failed`; 단일 실패는 깨끗한 `origin/main`에서도
    동일 재현된 `batch_recollect` 테스트 DB 환경 문제

### 보호 대상 checkout

`C:\projects\naver_cafe_archive`는 동기화 대상으로 사용하지 않는다.

- 브랜치: `main`
- HEAD: `9030076`
- `origin/main`보다 13커밋 뒤
- 추적 수정:
  - `docs/DEPLOY_MINIPC.md`
  - `docs/rag_incremental_index_update.md`
  - `scripts/register_rag_index_schedule.ps1`
  - `scripts/run_rag_focused_tests.py`
  - `scripts/run_rag_incremental_notify.py`
  - `tests/test_rag_focused_tests.py`
  - `tests/test_run_rag_incremental_notify.py`
- 미추적 보호 파일: `scripts/_step3_verify_v2.py`

위 변경은 다른 RAG 작업과 섞여 있으므로 소유 확인 전 정리·이동·stash·reset하지 않는다.

`C:\projects\ai_moneyingbot_rag_agent`는 `agent/rag-ingest-boundary` 전용 worktree이며,
별도 지시 전까지 수정하거나 병합하지 않는다.

## 3. 작업 시작 명령

```powershell
Set-Location "C:\projects\ai_moneyingbot_laptop_sync"
git fetch origin
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git log --oneline --decorate -10 origin/main
git log -1 --oneline --decorate origin/agent/rag-ops-hardening-20260724
git merge-base --is-ancestor origin/agent/rag-ops-hardening-20260724 origin/main
```

마지막 명령의 종료코드가 0이면 하드닝 브랜치가 `origin/main`에 포함된 것이고, 1이면 아직 미병합이다.
이 확인은 읽기 전용이며 병합을 수행하지 않는다.

## 4. 보고 원칙

- 작업 전: 무엇을/왜/영향 범위를 3줄 이내로 보고한다.
- 완료 후: 실행 명령과 실제 출력, 종료코드, 테스트 passed 수를 기록한다.
- 선택지는 `1, 2, 3`으로 제시한다.
- 세션 종료 시 `HANDOFF.md` 최상단에 새 항목을 추가한다.
- 문서와 코드 커밋·푸시는 오너 승인 후에만 한다.
