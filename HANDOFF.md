# HANDOFF — 2026-07-02

## 상태: 아카이브봇 정상 작동 (검증 완료)

네이버가 멤버 작성글 목록(/f-e/, /ca-fe/)을 클라이언트 렌더 SPA로 바꿔 HTML 파싱이 0행이 됐던 고장을 **REST API 직접 호출 방식으로 전환**해 해결. 커밋 `36a7746`.

- 제목 수집: `apis.naver.com/cafe-web/cafe-mobile/CafeMemberNetworkArticleListV3` (SPA 번들에서 확인한 실제 API). 클라이언트: [src/member_api.py](src/member_api.py)
- 로그인 판별의 신뢰 근거는 이제 이 API의 `code 0004` (HTML 휴리스틱은 SPA 셸에서 무력).
- 실검증: 밀린 제목 36건 + 본문 36/36 수집 성공. DB 43,491건 / max_id 172512. 테스트 306개 통과.
- 8각도 독립 리뷰 → 12건 검증 → 확정 문제 전부 수정 → 재리뷰 클리어.

## 운영 방법
`run_archive_bot_local.ps1` 한 번만 실행. 이미 로그인돼 있으면 Enter 없이 시작(무인 재시작 가능). 로그인 풀리면 명확히 멈추고 로그인 페이지를 열어줌.

## 주의사항
- 네이버 로그인 시 **"로그인 상태 유지" 반드시 체크** (안 하면 브라우저 종료 시 세션 소멸).
- 봇 강제종료 시 `state\archive_loop.lock`이 남아 30분간 재실행 차단 → 파일 삭제 후 재실행.
- venv python + 시스템 python 2개 프로세스로 보이는 건 정상(부모+자식), 중복 실행 아님.

## 남은 개선 후보 (급하지 않음)
- 백로그 모드 `--estimate 2828` 기본값이 15개/페이지 기준 → API는 20개/페이지라 재보정 필요 (실시간 수집엔 영향 없음).
- captcha/본인인증 등 비로그인 차단신호가 API 경로에선 미분류(generic error)로 뭉개짐.
- index_tail.py / index_tail_realtime.py 중복 → 공용 모듈로 통합하면 다음 네이버 변경 시 한 곳만 수정.
- 스냅샷이 2026-05-02 고정이라 collect-after-snapshot이 매번 ~26페이지 재스캔 (결과는 정상, 약간 느릴 뿐).
