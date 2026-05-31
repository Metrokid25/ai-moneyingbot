Title: Add RAG retrieval regression suite

Context:
- RAG fixture retrieval eval exists for a small in-memory retrieval-ready path.
- Golden question fixtures may provide reusable query-to-source expectations.
- The next step is to expand this into a focused retrieval regression suite.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-side work and must not be implemented in this RAG Bot worktree.

Goals:
- Add a retrieval regression suite that verifies expected documents or chunks are present in top-k results for representative questions.
- Reuse golden question fixtures if available.
- Prefer in-memory or retrieval-ready boundaries over live vector DB usage.
- Verify that each query retrieves a chunk with the expected source metadata.
- Keep tests independent of qdrant_client and other optional external dependencies.
- Avoid external LLM/API calls.
- Add the suite to scripts/run_rag_focused_tests.py if reliable.
- Do not write archive.db.
- Do not modify data/ originals.
- Do not access Naver Cafe.
- Do not touch archive crawler/parser/collector/browser code.

Allowed implementation files for next task:
- tests/test_rag_retrieval_regression.py
- tests/fixtures/
- scripts/run_rag_focused_tests.py
- tests/test_rag_focused_tests.py
- docs/rag_autorunner.md if a small focused-test note is needed

Expected verification for next task:
- pytest tests/test_rag_retrieval_regression.py --basetemp=.tmp\pytest
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
- retrieval regression cases run on fixtures or temporary data.
- expected source metadata appears in top-k results.
- tests pass without optional external dependencies.
- focused test runner includes the suite if it is reliable.
- no archive-owned files are touched.
