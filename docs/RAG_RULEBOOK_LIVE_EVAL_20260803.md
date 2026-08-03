# Rulebook v2 RAG 라이브 평가 — 2026-08-03

## 결과

미니PC production RAG index에서 Rulebook v2 gold 24문항을 1회 평가했다. 24개 지정 청크는
manifest와 Qdrant payload에 모두 존재했고 `article_id` 불일치나 빈 본문은 없었다. rerank는 dense보다
크게 개선됐지만 지정 근거 기준 3문항은 top-10 밖이었다.

| 지표 | Dense | Rerank | 차이 |
|---|---:|---:|---:|
| recall@1 | 0.4583 | 0.8333 | +0.3750 |
| recall@5 | 0.7083 | 0.8750 | +0.1667 |
| recall@10 | 0.8333 | 0.8750 | +0.0417 |
| MRR@10 | 0.5678 | 0.8542 | +0.2864 |
| top-10 회수 문항 | 20/24 | 21/24 | +1 |

실측 보고서:

- `artifacts/rulebook_v2/evaluation/rag_rulebook_eval_live_20260803.json`
- `artifacts/rulebook_v2/evaluation/rag_rulebook_miss_diagnostics_live_20260803.json`
- `artifacts/rulebook_v2/evaluation/rag_rulebook_index_verify_live_20260803.json`

## 실행 조건

- 미니PC RAG checkout: `C:\projects\naver_cafe_archive_rag`, HEAD `06b5b68`
- collection: `goodmorning_chunks`
- manifest: 51,040줄
- gold: 24문항, 24개 고유 지정 청크
- dense fetch: 50, 평가 depth: 10, rerank: Voyage `rerank-2`
- 실행 전 태스크: `RAG-IncrementalIndex=Ready`, 최근 결과 0
- Archive DB·Qdrant·manifest·스케줄에는 쓰지 않았다. 결과 JSON과 임시 실행 파일만 `%TEMP%`에 썼다.

## 지정 근거 미회수 3문항

### GM-R01 핵심 질문

- 지정 청크: `173480:0`
- dense fetch-50: 없음
- rerank top-10: 없음
- 직접 Qdrant 조회에서는 청크와 본문이 정상 존재했다.
- 판정: 최신 근거가 색인에 없어서가 아니라, 넓은 “변동성 장세의 위험 대응” 질의에서 오래된 유사 글들에
  밀린 실제 검색 미회수다. 최신성 가중 또는 규칙명·핵심 문구를 포함한 질의 변형 연구 대상이다.

### GM-R02 핵심 질문

- 지정 청크: `53601:0`, `7938:0`
- dense fetch-50 지정 근거 최고 순위: 19
- rerank top-10: 지정 근거 없음
- 대신 상위에는 `396:0`, `8471:0`, `3144:0`처럼 “주식은 종합주가지수를 사는 게임”을 직접 설명하는
  동의 근거가 배치됐다.
- 판정: 답변 의미 품질과 엄격한 지정-ID recall이 갈리는 사례다. 임의로 gold를 완화하지 말고, 이 동의
  근거를 Rulebook 보조 근거로 추가할지 별도 원문 리뷰 후 결정한다.

### GM-R11 예외 질문

- 지정 청크: `38039:0`, `13584:0`
- dense fetch-50 지정 근거 최고 순위: 16
- rerank top-10: 지정 근거 없음
- rerank 상위에는 거래량 증가와 분할 익절을 다룬 유효 글들이 있었고 기존 근거 `27421:0`도 9위였지만,
  질문이 요구한 “모든 거래량 증가가 동일하지 않다”는 예외 근거는 회수하지 못했다.
- 판정: 부분 답변은 가능하지만 다중근거 완결성은 실패다. caveat/contrast 질문의 별도 검색 또는 근거 역할별
  coverage 평가가 필요하다.

참고로 `GM-R06-02`는 dense top-10 밖이었지만 rerank 1위로 복구됐다.

## 원문·색인 검증

- Rulebook 생성기의 Archive union 읽기전용 검증:
  `validation=passed`, 12규칙, 24개 고유 article, 원문 인용 36/36 일치,
  `archive_union_count=43789`, `query_only=true`.
- production manifest: 지정 청크 24/24 존재.
- production Qdrant 직접 UUID 조회: 24/24 payload 존재, `article_id` 불일치 0, 빈 text 0.

따라서 이번 실패를 누락 색인이나 잘못된 `article_id`로 설명할 근거는 없다.

## 다음 판단

1. 현재 24문항 fixture는 변경하지 않고 기준선으로 동결한다.
2. strict evidence recall과 semantic answer relevance를 분리 보고한다.
3. R01은 최신성/핵심문구 query variant, R11은 evidence-role coverage 검색을 다음 RAG 연구 후보로 둔다.
4. R02의 동의 근거 3건은 Archive 원문 독립리뷰 후 Rulebook 보조 근거 편입 여부를 결정한다.
5. 이 평가 결과는 Trading Bot 수익성이나 실거래 적용 승인과 무관하다.
