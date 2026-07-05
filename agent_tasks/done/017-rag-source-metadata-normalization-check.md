Title: Add RAG source metadata normalization checks

Context:
- RAG ingest, chunking, retrieval, and answer output now preserve source metadata through focused tests.
- The next step is to verify that metadata names and shapes remain consistent across the RAG flow.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-side work and must not be implemented in this RAG Bot worktree.

Goals:
- Add fixture-based checks for source metadata normalization across ingest, chunking, retrieval, and answer boundaries.
- Verify fields such as source_id, title, url, source_path, chunk_id, and created_at/archived_at style dates where available.
- Detect missing fields, inconsistent names, and type mismatches.
- Keep tests independent of qdrant_client and other optional external dependencies.
- Avoid external LLM/API calls and live vector DB usage.
- Add focused tests that can be included in scripts/run_rag_focused_tests.py if reliable.
- Do not write archive.db.
- Do not modify data/ originals.
- Do not access Naver Cafe.
- Do not touch archive crawler/parser/collector/browser code.

Allowed implementation files for next task:
- src/rag_answering.py
- src/rag_answer_context.py
- src/rag_chunking.py
- tests/test_rag_source_metadata_normalization.py
- tests/fixtures/
- scripts/run_rag_focused_tests.py
- tests/test_rag_focused_tests.py
- docs/rag_autorunner.md if a small focused-test note is needed

Expected verification for next task:
- pytest tests/test_rag_source_metadata_normalization.py --basetemp=.tmp\pytest
- python scripts/run_rag_focused_tests.py
- git status -sb
- git diff --stat

Forbidden:
- git add .
- agent_tasks/pending/001-real-daily-archive-wiring.md implementation
- .env modification
- archive.db write/delete/reset
- data/ original modification/deletion
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
- source metadata normalization checks cover the current RAG fixture flow.
- missing/name/type mismatches produce clear failures.
- tests pass without optional external dependencies.
- focused test runner includes the test if it is reliable.
- no archive-owned files are touched.
