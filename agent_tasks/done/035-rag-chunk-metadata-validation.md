Title: Add RAG chunk metadata validation

Context:
- Chunk metadata flows through ingest, retrieval, and answer citation display.
- Missing or malformed metadata should be caught before it reaches answer
  assembly.

Goals:
- Add fixture-backed validation for required chunk metadata fields.
- Prefer a focused test over broad refactoring.
- Keep validation inside RAG chunking or ingest-export boundaries.

Allowed scope:
- `src/rag_chunking.py`
- `scripts/ingest_archive_export.py`
- `tests/test_rag_chunking.py`
- `tests/test_ingest_archive_export.py`
- `tests/fixtures/`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_chunking.py tests/test_ingest_archive_export.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Chunk metadata requirements are covered by focused tests.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
