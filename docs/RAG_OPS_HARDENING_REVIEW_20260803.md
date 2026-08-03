# RAG 운영 하드닝 독립 리뷰 — 2026-08-03

## 결론

원격 커밋 `3821e234ab1ff904e12d799f81cc3dc826b72527`에서 P0~P2 결함을 찾지 못했다.
현재 main 위에 충돌 없이 적용되며 전체 suite가 통과했다. 오너 승인 후 작업 브랜치 정식 통합 후보로
권고한다.

## 검토한 변경

1. 스케줄 등록 계정을 `$env:USERDOMAIN\$env:USERNAME` 조합 대신
   `WindowsIdentity.GetCurrent().Name`으로 해석한다.
2. 마지막 수집글 생존신호를 `saved_at DESC` 전체 정렬 대신 `article_id DESC` primary-key 역순으로
   읽는다.
3. 위 동작의 회귀 테스트와 미니PC 배포 문서를 함께 갱신한다.

Windows 인증 토큰의 `Name`은 일반적인 로컬·도메인 계정에서 `DOMAIN\user` 형식이며, 코드가 빈 값이나
qualified 형식이 아닌 값을 등록 전에 거부한다. `article_id`는 이 Archive 계약에서 Naver 글의 단조 증가
교차키이자 SQLite INTEGER PRIMARY KEY다. `BODY_COLLECTED`를 만족하는 가장 높은 ID를 읽는 것은 forward
수집 생존신호 목적과 맞고 Archive DB에 인덱스를 추가하지 않는다.

## 실측 검증

- 커밋 자체 표적 테스트: `40 passed in 0.72s`, rc=0.
- PowerShell AST: `powershell_parse_errors=0`.
- commit diff check: rc=0.
- `origin/main=2df7479`과 `3821e23`의 `git merge-tree --write-tree`: rc=0, 충돌 없음.
- 최신 main 격리 worktree에 `cherry-pick -n`으로 적용 후 전체 suite:
  `747 passed in 15.85s`, rc=0.
- 최신 main 적용 상태 PowerShell AST 오류 0, `git diff --check` rc=0.

검토 중 main이나 원격 브랜치에 커밋·푸시·병합하지 않았다.

## 현재 미니PC와의 차이

미니PC 실제 RAG checkout `C:\projects\naver_cafe_archive_rag`는
`agent/rag-minipc-handoff-20260723`, HEAD `06b5b68`, 원격 main 대비 `ahead 2 / behind 9`다.
읽기전용 확인 결과 아직 구버전 두 줄을 사용한다.

- 스케줄 계정: `$env:USERDOMAIN\$env:USERNAME`
- 생존신호: `ORDER BY saved_at DESC`

현재 일일 태스크의 최근 결과는 0이므로 긴급 장애는 아니지만, 하드닝을 main에 통합한 뒤 승인된 배포
기준점으로 갱신해야 성능·SSH 재등록 문제가 해소된다.

## 권고 순서

1. `agent/rag-ops-hardening-20260724`를 최신 main 기준으로 재검증하고 오너 승인 후 통합한다.
2. 새 deploy baseline commit/tag를 오너가 확정한다.
3. 미니PC에서 현재 태스크 Action·WorkingDirectory와 Qdrant/manifest 자산 위치를 읽기전용 스냅샷한다.
4. 운영 checkout을 임의 reset/clean하지 말고, 승인된 커밋으로 이동할 별도 clean runtime checkout을 준비한다.
5. 자산 안전 게이트와 `--dry-run --no-telegram`을 통과한 뒤 스케줄을 새 runtime 경로로 재등록한다.
6. 수동 1회 실행, `LastTaskResult=0`, 텔레그램 수신, 다음 정규 16:30 실행을 확인한다.
7. 기존 `06b5b68` checkout은 최소 2회 성공 전까지 rollback 용도로 보존한다.

2~7은 운영 변경이므로 별도 배포 승인 전 실행하지 않는다.
