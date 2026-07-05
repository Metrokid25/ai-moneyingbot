Title: Add RAG web UI smoke regression

Context:
- The local RAG web UI should continue rendering core controls and answer
  surfaces as backend behavior evolves.

Goals:
- Add or tighten a smoke test for the RAG web UI.
- Keep the test local and deterministic.
- Avoid adding external browser, crawler, or Cafe dependencies.

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
- The RAG web UI has focused smoke coverage for the selected behavior.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
