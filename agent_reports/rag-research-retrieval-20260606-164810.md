# RAG Research Question Retrieval Report

- generated_at: 20260606-164810
- db_only: true
- backend_status: unavailable
- backend_reason: collection_missing: goodmorning_chunks
- questions_file: agent_reports\rag-research-questions-20260601-154441.jsonl
- question_count: 11
- top_k: 5
- retrieval_ok: 0
- retrieval_no_results: 0
- retrieval_backend_unavailable: 11
- qdrant_path: C:\projects\ai_moneyingbot_rag_agent\data\qdrant
- collection: goodmorning_chunks
- model: voyage-3-large

## Collection

- collection_exists: False

## Settings Alignment

- search_qdrant_phase2.py: uses rag_retrieval DEFAULT_QDRANT_PATH and DEFAULT_COLLECTION
- run_rag_research_retrieval.py: uses the same rag_retrieval defaults unless CLI overrides are passed
- evaluate_rag_retrieval_set.py: mock/dry-run evaluator; it does not open Qdrant
- run_rag_focused_tests.py: includes runner help and test coverage; it does not execute live retrieval

## Questions

### research_q_001

- status: backend_unavailable
- backend_status: unavailable
- topic: 금리/긴축/주식시장
- question: 금리 상승은 주식시장에 어떤 부담으로 작용하는가?
- source_refs: article_id:1001:chunk_id:1001:0, rag_eval_questions.jsonl:eval-001, rag_eval_questions.jsonl:eval-004, rag_eval_questions.jsonl:eval-010, rag_golden_questions.jsonl:golden-001, sample_articles.jsonl:article_id:1001

Retrieval backend unavailable: collection_missing: goodmorning_chunks

### research_q_002

- status: backend_unavailable
- backend_status: unavailable
- topic: 환율/외국인 수급/한국 증시
- question: 환율 급등은 한국 주식시장과 외국인 수급에 어떤 영향을 주는가?
- source_refs: article_id:1002:chunk_id:1002:0, rag_eval_questions.jsonl:eval-002, rag_eval_questions.jsonl:eval-005, rag_golden_questions.jsonl:golden-002, sample_articles.jsonl:article_id:1002

Retrieval backend unavailable: collection_missing: goodmorning_chunks

### research_q_003

- status: backend_unavailable
- backend_status: unavailable
- topic: 경기침체/시장 신호
- question: 경기침체 국면에서 주식시장은 어떤 신호를 먼저 반영하는가?
- source_refs: rag_eval_questions.jsonl:eval-007

Retrieval backend unavailable: collection_missing: goodmorning_chunks

### research_q_004

- status: backend_unavailable
- backend_status: unavailable
- topic: 유동성/긴축 장세
- question: 유동성 장세와 긴축 장세는 어떻게 다르게 해석해야 하는가?
- source_refs: rag_eval_questions.jsonl:eval-001

Retrieval backend unavailable: collection_missing: goodmorning_chunks

### research_q_005

- status: backend_unavailable
- backend_status: unavailable
- topic: 부동산/전세가율/대출
- question: 부동산 하락장에서 전세가율은 왜 중요한가?
- source_refs: rag_eval_questions.jsonl:eval-004

Retrieval backend unavailable: collection_missing: goodmorning_chunks

### research_q_006

- status: backend_unavailable
- backend_status: unavailable
- topic: 반도체/사이클/수급
- question: 반도체 사이클은 어떤 방식으로 판단해야 하는가?
- source_refs: rag_eval_questions.jsonl:eval-002, rag_eval_questions.jsonl:eval-005

Retrieval backend unavailable: collection_missing: goodmorning_chunks

### research_q_007

- status: backend_unavailable
- backend_status: unavailable
- topic: 금/안전자산/거시환경
- question: 금은 어떤 거시경제 환경에서 방어 자산으로 해석되는가?
- source_refs: rag_eval_questions.jsonl:eval-003

Retrieval backend unavailable: collection_missing: goodmorning_chunks

### research_q_008

- status: backend_unavailable
- backend_status: unavailable
- topic: 거래량/차트/위험 신호
- question: 거래량 증가는 언제 긍정 신호이고 언제 위험 신호인가?
- source_refs: rag_eval_questions.jsonl:eval-006

Retrieval backend unavailable: collection_missing: goodmorning_chunks

### research_q_009

- status: backend_unavailable
- backend_status: unavailable
- topic: 리스크/손절/익절
- question: 손절 기준은 어떤 상황에서 필요하다고 설명되는가?
- source_refs: rag_eval_questions.jsonl:eval-006

Retrieval backend unavailable: collection_missing: goodmorning_chunks

### research_q_010

- status: backend_unavailable
- backend_status: unavailable
- topic: 테마주/매매/수급
- question: 테마주 매매에서 가장 경계해야 할 조건은 무엇인가?
- source_refs: rag_eval_questions.jsonl:eval-002, rag_eval_questions.jsonl:eval-005

Retrieval backend unavailable: collection_missing: goodmorning_chunks

### research_q_011

- status: backend_unavailable
- backend_status: unavailable
- topic: 정책/규제/업종
- question: 정책이나 규제 변화는 업종 투자 판단에 어떻게 반영해야 하는가?
- source_refs: rag_eval_questions.jsonl:eval-009

Retrieval backend unavailable: collection_missing: goodmorning_chunks
