# RAG DB-only Research Question Candidates

- generated_at: 20260601-154441
- db_only: true
- question_count: 11
- chunks_or_article_paths:
  - C:\projects\ai_moneyingbot_rag_agent\tests\fixtures\sample_articles.jsonl
- eval_paths:
  - C:\projects\ai_moneyingbot_rag_agent\tests\fixtures\rag_eval_questions.jsonl
  - C:\projects\ai_moneyingbot_rag_agent\tests\fixtures\rag_golden_questions.jsonl

## Source Counts

- C:\projects\ai_moneyingbot_rag_agent\tests\fixtures\rag_eval_questions.jsonl: 10
- C:\projects\ai_moneyingbot_rag_agent\tests\fixtures\rag_golden_questions.jsonl: 2
- C:\projects\ai_moneyingbot_rag_agent\tests\fixtures\sample_articles.jsonl: 4

## Filtered Topics

- none

## Candidates

### research_q_001

- question: 금리 상승은 주식시장에 어떤 부담으로 작용하는가?
- topic: 금리/긴축/주식시장
- generated_from: chunk_keyword, existing_eval, source_metadata, title
- source_refs: article_id:1001:chunk_id:1001:0, rag_eval_questions.jsonl:eval-001, rag_eval_questions.jsonl:eval-004, rag_eval_questions.jsonl:eval-010, rag_golden_questions.jsonl:golden-001, sample_articles.jsonl:article_id:1001
- status: candidate

### research_q_002

- question: 환율 급등은 한국 주식시장과 외국인 수급에 어떤 영향을 주는가?
- topic: 환율/외국인 수급/한국 증시
- generated_from: existing_eval, source_metadata, title
- source_refs: article_id:1002:chunk_id:1002:0, rag_eval_questions.jsonl:eval-002, rag_eval_questions.jsonl:eval-005, rag_golden_questions.jsonl:golden-002, sample_articles.jsonl:article_id:1002
- status: candidate

### research_q_003

- question: 경기침체 국면에서 주식시장은 어떤 신호를 먼저 반영하는가?
- topic: 경기침체/시장 신호
- generated_from: existing_eval
- source_refs: rag_eval_questions.jsonl:eval-007
- status: candidate

### research_q_004

- question: 유동성 장세와 긴축 장세는 어떻게 다르게 해석해야 하는가?
- topic: 유동성/긴축 장세
- generated_from: existing_eval
- source_refs: rag_eval_questions.jsonl:eval-001
- status: candidate

### research_q_005

- question: 부동산 하락장에서 전세가율은 왜 중요한가?
- topic: 부동산/전세가율/대출
- generated_from: existing_eval
- source_refs: rag_eval_questions.jsonl:eval-004
- status: candidate

### research_q_006

- question: 반도체 사이클은 어떤 방식으로 판단해야 하는가?
- topic: 반도체/사이클/수급
- generated_from: existing_eval
- source_refs: rag_eval_questions.jsonl:eval-002, rag_eval_questions.jsonl:eval-005
- status: candidate

### research_q_007

- question: 금은 어떤 거시경제 환경에서 방어 자산으로 해석되는가?
- topic: 금/안전자산/거시환경
- generated_from: existing_eval
- source_refs: rag_eval_questions.jsonl:eval-003
- status: candidate

### research_q_008

- question: 거래량 증가는 언제 긍정 신호이고 언제 위험 신호인가?
- topic: 거래량/차트/위험 신호
- generated_from: existing_eval
- source_refs: rag_eval_questions.jsonl:eval-006
- status: candidate

### research_q_009

- question: 손절 기준은 어떤 상황에서 필요하다고 설명되는가?
- topic: 리스크/손절/익절
- generated_from: existing_eval
- source_refs: rag_eval_questions.jsonl:eval-006
- status: candidate

### research_q_010

- question: 테마주 매매에서 가장 경계해야 할 조건은 무엇인가?
- topic: 테마주/매매/수급
- generated_from: existing_eval
- source_refs: rag_eval_questions.jsonl:eval-002, rag_eval_questions.jsonl:eval-005
- status: candidate

### research_q_011

- question: 정책이나 규제 변화는 업종 투자 판단에 어떻게 반영해야 하는가?
- topic: 정책/규제/업종
- generated_from: existing_eval
- source_refs: rag_eval_questions.jsonl:eval-009
- status: candidate
