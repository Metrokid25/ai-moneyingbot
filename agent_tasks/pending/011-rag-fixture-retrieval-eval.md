# Add RAG fixture retrieval eval

Goal:
- Add a fixture-based RAG retrieval evaluation task that builds on the fixture JSONL smoke test and verifies retrieval behavior without Archive Bot state, real vector DB services, or external answer generation APIs.

Context:
- 010 added a fixture JSONL smoke test for the ingest -> chunking -> retrieval-ready boundary.
- The next step is to add a focused retrieval eval that checks whether fixture queries find the expected chunk or document metadata.
- `agent_tasks/pending/001-real-daily-archive-wiring.md` is Archive-side work and must not be touched or implemented in this task.

Requirements:
1. Do not use the real `archive.db`, real `data/` originals, or Naver Cafe.
2. Use only fixture JSONL files or pytest `tmp_path` temporary files.
3. Include at least two fixture documents.
4. Verify that each query returns the expected document or chunk in the top results.
5. Ensure the test passes without optional dependencies such as `qdrant_client`.
6. If a real vector DB would be required, do not use it; validate an in-memory path or retrieval-ready boundary that fits the current code structure.
7. Verify source metadata is preserved through retrieval result/context:
   - `source_id`
   - `title`
   - `url` or `source_path`
   - article/chunk identifiers where applicable
8. Design the eval so it can be included in the existing RAG focused test runner.
9. Do not depend on external answer generation APIs.
10. Success conditions:
    - two or more fixture documents are prepared
    - each query includes the expected document or chunk in top results
    - source metadata preservation is verified
    - `python scripts/run_rag_focused_tests.py` passes

Suggested implementation files:
- tests/test_rag_fixture_retrieval_eval.py
- tests/fixtures/
- scripts/run_rag_focused_tests.py
- docs/rag_autorunner.md if documenting the new focused eval is useful

Expected verification:
- python scripts/run_rag_focused_tests.py
- pytest tests/test_rag_fixture_retrieval_eval.py --basetemp=.tmp\pytest
- git status -sb
- git diff --stat

Forbidden:
- git add .
- Implementing `agent_tasks/pending/001-real-daily-archive-wiring.md`
- `.env` modification
- `archive.db` write/delete/reset
- `data/` original modification/deletion
- actual Naver Cafe access
- external answer generation API calls
- scripts/_step3_verify_v2.py
- scripts/daily_archive.py
- scripts/index_tail.py
- scripts/batch_recollect.py
- src/browser.py
- src/parser.py
- src/collector.py
- src/indexer.py

Completion criteria:
- Fixture-based retrieval eval exists and is RAG-only.
- It uses only fixture and temporary paths.
- It verifies expected top retrieval results for multiple queries.
- It verifies source metadata preservation.
- It is included in the focused RAG test runner if it remains reliable.
- No Archive-owned files are touched.
