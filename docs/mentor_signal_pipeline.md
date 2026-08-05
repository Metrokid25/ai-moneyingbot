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
과거 회상, 뉴스, 비교 선호 및 섹터 단독 언급을 구분한다. 불명확하거나 이름/코드가
불일치하면 `REVIEW_REQUIRED`이며 자동 등록하지 않는다.

본문을 HTML 제거·공백 정규화한 뒤 SHA-256을 계산한다. Reader와 Trading 양쪽 모두
`(article_id, article_revision_hash, stock_code, signal_type)` UNIQUE 키로 중복을
차단한다. 수정 본문은 새 해시이므로 재판독하지만 삭제된 과거 매수 의견을 자동
매도 신호로 바꾸지는 않는다.

첫 실행은 기존 `MAX(article_id)`와 현재 시각을 기준점으로 저장하고 종료하므로 전체
과거 글을 재처리하지 않는다. Fixture/명시적 백필에만 `--bootstrap-existing`을 쓴다.

## 모드

- `shadow`(기본): 판독·상태 저장·Telegram만 수행. Trading API를 호출하지 않는다.
- `paper`: 신뢰도 기준 이상의 `ADD_WATCH`만 Trading API에 전달한다.
- `live`: 코드 정책으로 즉시 오류 종료한다.

Trading API도 `mode=paper`, `KIS_ENV=PAPER`, 정확한 작성자, `ADD_WATCH`, 신뢰도,
종목명/코드 일치를 다시 검증한다. API에는 주문 함수 호출이나 `main.py` 배선이 없다.
