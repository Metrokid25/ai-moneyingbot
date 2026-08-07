# Mentor Signal Pipeline

## 목적과 경계

이 기능은 멘토 게시글을 주문 명령으로 바꾸지 않는다. Archive Bot이 소유한
`archive.db`에서 새 본문을 읽고 검증된 관심종목 후보만 Trading Bot에 전달한다.
Trading Bot은 후보를 활성 Paper 유니버스에 추가하며, 실제 모의 진입 여부는 기존
`strategy.paper_runner`의 전략 조건이 결정한다.

```text
Naver Cafe -> Archive Bot -> archive.db (read-only)
  -> Mentor Signal Reader -> reader state DB
  -> POST /api/signals/mentor -> trading.db paper watchlist
  -> existing Paper Runner strategy -> paper records/Telegram
```

- Archive Bot만 `archive.db`에 쓴다.
- Mentor Signal Reader는 자체 `mentor_signals.db`에 체크포인트와 판독 결과를 쓴다.
- Trading Bot만 `trading.db`에 관심종목과 수신 감사로그를 쓴다.
- Reader는 `trading.db`를 열지 않는다. 종목 마스터는 Trading Bot이 내보낸 전용
  읽기 스냅샷만 소비한다.

## 판독과 멱등성

규칙 판독은 종목명/코드 정확 일치, 관심·주시 표현, 추격/매수 금지, 정리/매도,
과거 회상, 뉴스, 비교 선호 및 섹터 단독 언급을 구분한다. 아카이브 43,506건의
작성 습관을 반영해 다음 제목군을 별도로 처리한다.

- 제목이 정확한 종목명: 본문이 비었거나 제목만 반복돼도 `ADD_WATCH` 후보(0.995)
- 제목에 `특징주`: 본문의 종목 단독행/구조화 목록을 후보(0.98)로 판독
- `오늘은/이번주는/다음주는`: 거시 설명 전체가 아니라 하단 25%의 구조화 종목
  블록만 후보(0.96)로 판독

각 종목의 가장 뒤쪽 명시 행동을 다시 확인해 추격 금지·매수 금지·정리 지시를
우선한다. 외인/기관 매도나 공매도 설명은 멘토의 `EXIT_SIGNAL`로 간주하지 않고,
뉴스·과거 회상에 나온 종목도 구조화 목록 기본 픽으로 되살리지 않는다. 한 글에
서로 다른 종목 행동이 있으면 종목별 감사 이벤트로 나누며 자동 전달은 그중
`ADD_WATCH`만 가능하다. 불명확하거나 이름/코드가 불일치하면 `REVIEW_REQUIRED`다.

제목과 본문의 의미 있는 줄 경계를 정규화한 뒤 SHA-256을 계산한다. 제목 자체와
목록 줄 경계가 판독 의미이므로 제목/구조 변경도 새 revision이다. Reader와 Trading 양쪽 모두
`(article_id, article_revision_hash, stock_code, signal_type)` UNIQUE 키로 중복을
차단한다. 수정 본문은 새 해시이므로 재판독하지만 삭제된 과거 매수 의견을 자동
매도 신호로 바꾸지는 않는다.

첫 실행은 해당 멘토의 기존 `MAX(article_id)`와 현재 시각을 하나의 트랜잭션으로
기준점에 저장하고 종료하므로 전체
과거 글을 재처리하지 않는다. Fixture/명시적 백필에만 `--bootstrap-existing`을 쓴다.

## 모드

- `shadow`(기본): 판독·상태 저장·Telegram만 수행. Trading API를 호출하지 않는다.
- `paper`: 신뢰도 기준 이상의 `ADD_WATCH`만 Trading API에 전달한다.
- `live`: 코드 정책으로 즉시 오류 종료한다.

Trading API도 `mode=paper`, `KIS_ENV=PAPER`, 정확한 작성자, `ADD_WATCH`, 신뢰도,
종목명/코드 일치를 다시 검증한다. API에는 주문 함수 호출이나 `main.py` 배선이 없다.
