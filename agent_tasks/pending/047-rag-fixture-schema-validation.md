Title: Add RAG fixture schema validation

Context:
- RAG JSONL fixtures are shared by ingest, retrieval, and evaluation tests.
- A compact schema validation test can catch fixture drift before it causes
  unclear downstream failures.

Goals:
- Add validation for required RAG fixture fields and simple type expectations.
- Keep validation local to tests and existing fixtures.
- Prefer clear assertion messages over broad framework changes.

Allowed scope:
- `tests/fixtures/`
- `tests/test_rag_fixture_jsonl_smoke.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_fixture_jsonl_smoke.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Fixture schema expectations are covered by focused tests.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
