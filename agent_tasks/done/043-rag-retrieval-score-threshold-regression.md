Title: Add RAG retrieval score threshold regression

Context:
- Retrieval score thresholds should keep weak matches from being presented as
  grounded evidence.
- A fixture-level regression can document the expected boundary without
  external vector services.

Goals:
- Add or tighten a deterministic regression for retrieval score thresholding.
- Use synthetic or in-repo fixture records only.
- Keep the expected threshold behavior clear in assertions.

Allowed scope:
- `src/rag_retrieval.py`
- `tests/test_rag_retrieval*.py`
- `tests/fixtures/`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_retrieval.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Retrieval score threshold behavior is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
