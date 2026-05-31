Title: Improve RAG focused test runner coverage

Context:
- The focused RAG test runner is the autorunner safety gate for RAG-owned work.
- New RAG tests should be easy to include without broad, unrelated test runs.

Goals:
- Add or tighten coverage for the focused RAG test runner command list.
- Include missing RAG-only tests when appropriate.
- Keep the runner free of archive collection or write commands.

Allowed scope:
- `scripts/run_rag_focused_tests.py`
- `tests/test_rag_focused_tests.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_focused_tests.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Focused runner coverage reflects current RAG-owned tests.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
