Title: Add RAG retrieval ranking regression

Context:
- Retrieval ranking quality can drift when scoring or result normalization changes.
- The planner needs a backlog candidate that stays fully inside fixture-backed RAG
  retrieval behavior.

Goals:
- Add a deterministic regression for ranking multiple candidate chunks.
- Prefer synthetic records or existing fixtures over external services.
- Document the expected ranking signal in the test name or assertion.

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
- Ranking behavior is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
