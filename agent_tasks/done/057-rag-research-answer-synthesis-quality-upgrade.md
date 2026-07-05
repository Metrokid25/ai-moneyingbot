# 057 RAG Research Answer Synthesis Quality Upgrade

Status: done

## Scope

- Upgrade DB-only research answer drafts from preview concatenation to conclusion-oriented synthesis.
- Keep answers grounded only in retrieval report title, preview, score, and source metadata.
- Preserve `used_sources`, `source_ref`, and existing `no_evidence` / `backend_unavailable` branches.
- Avoid external search, market data, news, LLM calls, and Archive-owned code.

## Validation

- `pytest tests/test_rag_research_answers.py --basetemp=.tmp/rag_research_answers_pytest`
- `python scripts/run_rag_focused_tests.py`
- `python scripts/run_rag_research_answers.py --retrieval-file agent_reports/rag-research-retrieval-20260606-174814.jsonl`
- `git diff --check`
