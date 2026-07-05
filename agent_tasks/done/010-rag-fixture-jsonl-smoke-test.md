# Add RAG fixture JSONL smoke test

Goal:
- Add a fixture-based smoke test that verifies the RAG read-only flow from archive-style JSONL input through ingest, chunking, and retrieval-ready output without using full pytest or Archive Bot state.

Context:
- Archive Bot produces archive-style JSONL artifacts.
- RAG Bot must treat those artifacts as read-only inputs.
- The smoke test should prove that ingest -> chunking -> retrieval preparation still works with a representative fixture.
- `agent_tasks/pending/001-real-daily-archive-wiring.md` is Archive-side work and must not be touched or implemented in this task.

Requirements:
1. Use fixture JSONL only.
2. Do not open or write the real `archive.db`.
3. Do not modify real `data/` originals.
4. Do not access Naver Cafe.
5. Validate only the RAG ingest/chunk/retrieval boundary.
6. Use `.tmp` or pytest `tmp_path` for generated outputs.
7. Design the smoke test so it can be included in the existing RAG focused test runner.
8. Success conditions:
   - fixture JSONL import succeeds
   - chunk generation succeeds
   - source metadata preservation is verified
   - retrieval or retrieval-ready output is verified
   - `python scripts/run_rag_focused_tests.py` passes

Suggested implementation files:
- tests/test_rag_fixture_jsonl_smoke.py
- tests/fixtures/
- scripts/run_rag_focused_tests.py
- docs/rag_autorunner.md if documenting the new focused smoke check is useful

Expected verification:
- python scripts/run_rag_focused_tests.py
- pytest tests/test_rag_fixture_jsonl_smoke.py --basetemp=.tmp\pytest
- git status -sb
- git diff --stat

Forbidden:
- git add .
- Implementing `agent_tasks/pending/001-real-daily-archive-wiring.md`
- `.env` modification
- `archive.db` write/delete/reset
- `data/` original modification/deletion
- actual Naver Cafe access
- scripts/_step3_verify_v2.py
- scripts/daily_archive.py
- scripts/index_tail.py
- scripts/batch_recollect.py
- src/browser.py
- src/parser.py
- src/collector.py
- src/indexer.py

Completion criteria:
- Fixture JSONL smoke test exists and is RAG-only.
- The smoke test uses only fixture and temporary paths.
- The smoke test verifies ingest, chunking, metadata preservation, and retrieval-ready output.
- The focused RAG test runner includes the smoke test if it remains reliable.
- No Archive-owned files are touched.

## Completion note

Completed by:
- Implement RAG fixture JSONL smoke test

Verified:
- python scripts/run_rag_focused_tests.py
- pytest tests/test_rag_fixture_jsonl_smoke.py --basetemp=.tmp\pytest
- pytest tests/test_rag_focused_tests.py --basetemp=.tmp\pytest
- pytest tests/test_rag_autorunner_docs.py --basetemp=.tmp\pytest
- python scripts/agent_next_task.py --list
- git status -sb
