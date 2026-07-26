# Archive봇 노트북 개발 인수인계

> 노트북의 Archive 개발 작업 시작 정본이다. 채팅 요약만 믿지 말고 이 문서,
> `HANDOFF.md` 최신 항목, `docs/OWNERSHIP.md`,
> `docs/ARCHIVE_MINIPC_OPERATIONS.md`를 읽은 뒤 코드로 재확인한다.
> 별도 채팅 프롬프트는 필요 없다. 고정 커밋을 최신값으로 가정하지 않으며
> `git pull --ff-only origin main` 후 `origin/main`을 권위값으로 사용한다.

## 1. 노트북 작업 공간

현재 확인된 작업 공간은 다음과 같다.

| 경로 | 상태 | 사용 규칙 |
|---|---|---|
| `C:\tmp\naver_cafe_archive_archivefork` | Archive 전용 clean worktree | 노트북 Archive 개발 시작점 |
| `C:\projects\naver_cafe_archive` | RAG tracked 변경 7개와 미추적 `scripts/_step3_verify_v2.py` 존재 | pull/reset/clean/stash/checkout 금지, Archive 작업에 사용하지 않음 |

기본 저장소의 RAG 변경은 다른 담당자의 작업이다. 내용이 원격과 같아 보이더라도 임의로 되돌리거나
스테이징하지 않는다. 미추적 `scripts/_step3_verify_v2.py`도 삭제·수정·스테이징하지 않는다.

## 2. 첫 행동

다음 명령은 Archive 전용 clean worktree에서 실행한다.

```powershell
cd C:\tmp\naver_cafe_archive_archivefork
$dirty = @(git status --porcelain=v1)
if ($LASTEXITCODE -ne 0) { throw "git status failed" }
if ($dirty.Count -ne 0) { throw "tracked, staged, or untracked changes exist; stop" }
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw "git pull --ff-only origin main failed" }
$dirtyAfter = @(git status --porcelain=v1)
if ($LASTEXITCODE -ne 0) { throw "post-pull git status failed" }
if ($dirtyAfter.Count -ne 0) { throw "worktree became dirty after pull; stop" }
$headCommit = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "git rev-parse HEAD failed" }
$mainCommit = (git rev-parse origin/main).Trim()
if ($LASTEXITCODE -ne 0) { throw "git rev-parse origin/main failed" }
if ($headCommit -ne $mainCommit) { throw "HEAD does not equal origin/main; stop" }
git status --short --branch
```

- tracked/staged/untracked 변경이 있으면 merge로 덮거나 `git reset`, `git clean`, `git stash`로
  숨기지 말고 파일 목록을 보고한다.
- pull 후 worktree가 dirty이거나 `HEAD`가 `origin/main`과 다르면 원인을 확인하기 전 새 작업을 시작하지 않는다.
- 개발은 항상 `origin/main`에서 새 `agent/archive-*` 브랜치 또는 Codex의 새 worktree로 시작한다.
- `main` force push, `git add -A`, `Co-Authored-By`를 금지한다.

## 3. 현재 완료 상태

- Archive healthcheck, index-tail 단일 정본, Git 기반 미니PC 인수인계가 운영 반영됐다.
- 수동 snapshot/tail 일시 오류는 같은 페이지에서 최대 3회 재시도하며 차단 오류는 즉시 중단한다.
- 수동 tail estimate 미지정 기본값은 멤버 REST URL `2121`, 기존 HTML URL `2828`이며
  사용자가 `--estimate`를 명시하면 그 값이 우선한다.
- Enter 대기는 `src/console_io.py` 단일 helper를 사용하며, 구형
  `daily_archive.fetch_list_rows`와 `build_daily_archive_command`는 제거됐다.
- 최근 미니PC 라이브 검증은 `HEALTHY`, rc=0, controller instance 1개였다.
- 미니PC의 과거 로컬 HANDOFF 커밋 `91dc050`은
  `backup/archive-minipc-handoff-91dc050-20260724`에 보존돼 있다.

이 상태는 인수인계 시점 스냅샷이다. 작업 전 반드시 최신 `origin/main`과 실제 코드를 다시 확인한다.

## 4. 다음 개발 작업

- Enter-wait 중복과 죽은 코드 정리는 개발 PC 검증까지 완료됐다.
- 운영 코드 import 변경이므로 미니PC pull·재시작·60초 healthcheck가 남아 있으나,
  2026-07-26 오너 지시로 나중 패치 단계까지 보류한다.
- 그 외 남은 Archive 운영 이슈는 완전 로그오프 사각지대다. 작업 스케줄러와 로그인 세션 구조를
  바꾸는 별도 설계 작업이므로 오너 승인 전 착수하지 않는다.

## 5. 소유권과 절대 규칙

- Archive만 `archive.db`/`mentor.db`에 쓴다. articles 스키마는 동결이다.
- RAG 소유 파일은 수정하지 않는다:
  `scripts/notify_telegram.py`, `scripts/run_rag_incremental_notify.py`, `src/rag_*`.
- RAG/Qdrant와 trading-bot 저장소·데이터에 접근하거나 변경하지 않는다.
- 로그인 판별 권위는 `member_api.check_member_login()`의 API `code-0004`다.
- persistent browser profile은 동시에 한 프로세스만 사용한다.
- 수집기·프로필·DB를 사용하는 라이브 검증을 노트북에서 흉내 내지 않는다.

## 6. 작업 사이클

1. `git pull --ff-only origin main`과 clean 확인
2. 별도 브랜치/worktree
3. 테스트로 기존 계약 고정
4. 구현
5. `PYTHONUTF8=1` 전체 pytest
6. 독립 다각도 리뷰
7. 지적 수정과 전체 재검증
8. 오너 확인
9. `main` ff-only 반영과 push
10. 운영 코드면 미니PC 승인 범위를 정확히 받아 배포·재시작·60초 healthcheck
11. `HANDOFF.md` 최상단 기록

미니PC 작업은 메인 PC 공용 브리지
`C:\Users\재승\.codex\scripts\invoke-mini-bot-codex.ps1`를 사용한다.
상태 확인은 읽기 전용 기본 호출로 수행하며, pull·파일 수정·재시작·태스크 변경은 오너가 정확한 범위를
승인한 경우에만 `-AllowMutation -ApprovalNote`를 사용한다. 수동 명령 복사·붙여넣기를 오너에게 요구하지 않는다.

## 7. 완료 보고

- 브랜치, 기준 `origin/main`, 최종 커밋
- 변경 파일과 파일:라인 근거
- 관련/전체 테스트 수와 rc
- 독립 리뷰 지적과 수정 결과
- RAG 소유 파일·보호 파일 무변경 확인
- main 반영 여부
- 미니PC 변경이 있었다면 승인 범위, HEAD, 태스크, healthcheck, controller 수
- 다음 작업
