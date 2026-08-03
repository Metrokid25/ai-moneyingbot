# A등급 매매원칙 연구 인계 계약 v1

## 결론부터

`GM-R01`, `GM-R03`, `GM-R06`, `GM-R07`은 자동화 가능성이 상대적으로 높은 **연구 가설**이다.
수익성이 검증된 매매법이 아니며, 이 문서와 JSONL은 실거래 적용·자동 주문·Trading Bot 규칙 변경을
승인하지 않는다.

정본 JSONL:

`artifacts/trading_research/a_grade_rules_research_contract_v1.jsonl`

재현 생성기:

```powershell
$env:PYTHONUTF8='1'
python scripts/build_trading_research_contract.py --check-only
python scripts/build_trading_research_contract.py
```

## 소유권 경계

- RAG Bot은 근거와 실험 계약만 JSONL로 제공한다.
- 교차 키는 `article_id`다.
- RAG Bot은 Trading Bot 소유의 포지션·체결·주문·OHLCV를 읽거나 쓰지 않는다.
- Trading Bot 연구자는 자기 저장소와 데이터에서 실험하고, 결과만 아래 JSONL 계약으로 반환한다.
- Archive DB는 계속 Archive Bot 소유이며 RAG는 읽기전용이다.

## 연구 순서

1. Trading Bot 코드 커밋, 데이터 스냅샷, 종목군, 기간을 고정한다.
2. 각 계약의 baseline·candidate grid·주지표·가드레일 허용치를 실행 전에 등록한다.
3. 시간순 워크포워드 5개 이상 구간에서 비교한다.
4. 봉인 홀드아웃을 보지 않고 후보를 최대 1개 선택한다.
5. 선택 후보를 봉인 홀드아웃에서 단 한 번 평가한다.
6. 현재 Trading Bot의 버전 고정 비용과 더 불리한 스트레스 비용에서 반복한다.
7. 결과를 `trading_rule_research_result` schema_version 1 JSONL로 반환한다.

룩어헤드, 생존편향, 체결 불가능 가격, 사후 전략 태그가 발견되면 결과는
`invalid_experiment`다. 필수 분봉이나 전략 태그가 없으면 `not_evaluable`, 사전등록한 최소 표본에
못 미치면 `insufficient_sample`로 종료한다. 실패나 평가 불가는 계약 위반이 아니라 유효한 연구 결과다.

## 규칙별 핵심 비교

| 규칙 | 동일하게 고정할 것 | 바꿔 비교할 것 | 우선 위험지표 |
|---|---|---|---|
| GM-R01 | 진입·종목군·기간 | 위험회피 노출 상한 | MDD, 95% 꼬리손실 |
| GM-R03 | 진입 신호·목표비중 | 일괄진입 vs 계획 분할 | MDD, 불리한 가격변동 |
| GM-R06 | 추격 태그 진입 | 일반 보유 vs 시간·손실 제한 | 꼬리손실, 익일 갭위험 |
| GM-R07 | 진입과 전략군 태그 | 단일 손절 vs 전략군별 손절 | MDD, 꼬리손실, 순기대값 |

원문 숫자는 검증 후보일 뿐이다. 특히 20%, 3~5%, 10%를 보편 상수로 승격하지 않는다.

## 반환 파일 최소 조건

각 줄은 하나의 baseline-candidate 비교 결과이며 다음을 포함해야 한다.

- 계약·규칙·실험 ID
- Trading Bot 코드 커밋과 데이터 스냅샷 ID
- 기간·빈도·종목군·baseline·candidate·파라미터
- 수수료·세금·스프레드·슬리피지의 실제 사용값
- 워크포워드 구간별 지표와 봉인 홀드아웃 지표
- 유효 사건 수, 데이터 무결성 게이트 결과
- 결정값과 이유, 완전한 재현 명령

허용 결정값은 `retain_for_further_research`, `reject`, `insufficient_sample`,
`not_evaluable`, `invalid_experiment`다. 첫 값도 “실거래 승인”이 아니라 다음 연구 단계 후보라는 뜻이다.

## 금지

- RAG 저장소에서 Trading Bot 데이터 또는 상태를 직접 읽기
- JSONL을 주문·신호 입력으로 자동 연결
- 홀드아웃 결과를 본 뒤 파라미터·허용치를 수정하고 같은 결과를 확정값처럼 보고
- 비용·상장폐지·기업행사·체결 가능성을 빼고 수익성을 주장
- 오너의 별도 승인 없이 Trading Bot 코드, 배포, 모의·실거래 설정 변경
