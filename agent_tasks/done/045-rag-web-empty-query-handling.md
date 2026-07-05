Title: Add RAG web empty query handling regression

Context:
- The local RAG web UI should handle empty or whitespace-only questions without
  invoking retrieval or answer generation.
- This behavior is user-facing and should stay deterministic.

Goals:
- Add or tighten a smoke regression for empty query handling.
- Verify the UI response is clear and local.
- Avoid external browser, crawler, or Cafe dependencies.

Allowed scope:
- `scripts/serve_rag_web.py`
- `tests/test_rag_web.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_web.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Empty query handling is covered by a focused web UI regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
