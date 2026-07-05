Title: Add RAG retrieval source ordering regression

Context:
- Retrieval result ordering affects answer grounding and displayed sources.
- A small fixture-level regression can guard against accidental ordering drift.

Goals:
- Add a deterministic retrieval ordering test using synthetic or fixture data.
- Keep the test independent of external vector services.

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
- Retrieval ordering behavior is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
