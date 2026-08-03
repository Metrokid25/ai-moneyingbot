# Rulebook v2 RAG Gold 평가 계약

`tests/fixtures/rag_rulebook_gold_v2.jsonl`은 12개 매매원칙마다 핵심 질문 1개와 예외·금지·상충 질문
1개, 총 24개를 고정한다. 정답은 Rulebook v2의 근거 `article_id`와 실제 RAG manifest의
`chunk_id`다. 이 fixture는 검색 재현성을 평가하며 매매 수익성의 정답지가 아니다.

## 생성·정적 검증

```powershell
$env:PYTHONUTF8='1'
python scripts/build_rulebook_rag_gold.py --check-only
python scripts/build_rulebook_rag_gold.py
pytest tests/test_rulebook_rag_gold.py --basetemp=.tmp/pytest-rulebook-gold
```

## 라이브 평가

기존 평가기를 그대로 사용한다.

```powershell
$env:PYTHONUTF8='1'
python scripts/evaluate_rag_recall_gold.py `
  --gold tests/fixtures/rag_rulebook_gold_v2.jsonl `
  --qdrant-path data/qdrant `
  --collection goodmorning_chunks
```

실행은 질문 임베딩과 rerank API 호출 비용이 발생한다. 승인된 RAG 실행 환경에서만 수행하고,
보고서에는 RAG 코드 커밋, manifest 청크 수·최대 article_id, embedding/rerank 모델, 질문 수,
recall@1/5/10, MRR@10, 실패한 질문의 dense/rerank 순위를 기록한다.

## 판독 원칙

- `expected_chunk_ids` 중 하나가 검색되면 기존 평가기의 해당 질문 recall은 성공이다.
- 두 근거를 함께 요구하는 질문은 이후 원문 재확인 단계에서 `expected_evidence_roles`의 전체 역할을
  확인해야 한다. 기존 recall 수치 하나로 다중 근거가 전부 회수됐다고 주장하지 않는다.
- 점수가 낮으면 질문·청크·검색·rerank 중 어디서 실패했는지 원문 기준으로 분리 진단한다.
- fixture를 결과에 맞춰 임의 수정하지 않는다. 근거 오류가 확인될 때만 변경 이유와 전후 ID를 남긴다.
