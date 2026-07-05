# 054 RAG Research Question Retrieval Runner

Status: done

## Scope

- Add a DB-only retrieval runner for generated RAG research question JSONL files.
- Preserve question metadata and write structured retrieval JSONL plus readable Markdown reports.
- Do not generate answers in this step.

## Validation

- `pytest tests/test_rag_research_retrieval.py --basetemp=.tmp/rag_research_retrieval_pytest`
- `python scripts/run_rag_focused_tests.py`
- `python scripts/run_rag_research_retrieval.py --questions-file agent_reports/rag-research-questions-20260601-154441.jsonl --top-k 5`
- `git diff --check`
