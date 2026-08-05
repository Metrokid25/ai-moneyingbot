# Mentor Signal Safety

## 불변 안전장치

1. 기본 모드는 `shadow`다.
2. `live`는 CLI와 런타임 양쪽에서 거부한다.
3. Archive DB는 SQLite `mode=ro` URI로만 연다.
4. Trading API는 `X-Web-Key`, `MENTOR_AUTHOR_ID`, `KIS_ENV=PAPER`를 확인한다.
5. 자동 등록은 `ADD_WATCH`이면서 신뢰도 기준 이상인 정확한 종목명/코드 조합만 허용한다.
6. 추격 금지, 매수 금지, 정리/매도, 과거 회상, 단순 뉴스 및 섹터 단독 언급은 등록하지 않는다.
7. 관심종목 등록과 전략 진입은 분리한다. 시장가 즉시매수 코드는 없다.
8. `main.py` 실전 주문 엔진과 KIS 주문 메서드는 수정하거나 호출하지 않는다.

## 감사 데이터

Reader 상태 DB에는 원문 식별자, revision hash, 신호, 근거, 감지/처리 시각, 전달 상태와
Trading 응답을 남긴다. Trading DB에는 같은 멱등키, 작성자, 종목, 신뢰도, 근거,
수신/처리 시각과 응답을 남긴다. 원본 Archive DB에는 어떤 체크포인트도 쓰지 않는다.

## Paper 전환 게이트

- Shadow에서 작성자 필터가 실제 운영 글만 잡는지 확인
- 종목 마스터 스냅샷 갱신과 이름/코드 정확 일치 확인
- 부정/과거/비교/수정 게시글 오탐 검토
- Trading 웹앱이 `KIS_ENV=PAPER`로 실행 중인지 확인
- E2E fixture가 Paper Runner `load_universe`에 나타나는지 확인
- 운영자 승인 후 `MENTOR_SIGNAL_MODE=paper`로 변경
