# 056 RAG DB-grounded Research Answer Generator

Status: done

## Scope

- Add a DB-only answer draft generator for research retrieval JSONL reports.
- Use only retrieval report fields: question, topic, result title, preview, score, article_id, chunk_id, and source_ref.
- Distinguish `ok`, `weak_evidence`, `no_evidence`, and `backend_unavailable` answer statuses.
- Do not call external search, news, market data, LLMs, or Archive collection code.

## Validation

- `pytest tests/test_rag_research_answers.py --basetemp=.tmp/rag_research_answers_pytest`
- `python scripts/run_rag_focused_tests.py`
- `python scripts/run_rag_research_answers.py --retrieval-file agent_reports/rag-research-retrieval-20260606-174814.jsonl`
- `git diff --check`
