Title: Add RAG golden question fixtures

Context:
- Existing fixture tests cover RAG ingest, chunking, retrieval-ready output, answer citations, and no-context behavior.
- The next step is to create reusable representative question fixtures for retrieval and answer regression tests.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-side work and must not be implemented in this RAG Bot worktree.

Goals:
- Define a small golden question fixture structure based on existing RAG fixture/sample data.
- Include each question with expected source metadata such as source_id, title, url, and chunk_id where available.
- Make the fixture usable by future retrieval and answer regression tests.
- Keep tests fixture-based or pytest tmp_path-based.
- Avoid external LLM/API calls.
- Avoid live vector DB dependencies and qdrant_client requirements.
- Add focused tests that can be included in scripts/run_rag_focused_tests.py if reliable.
- Do not write archive.db.
- Do not modify data/ originals.
- Do not access Naver Cafe.
- Do not touch archive crawler/parser/collector/browser code.

Allowed implementation files for next task:
- tests/fixtures/
- tests/test_rag_golden_questions.py
- scripts/run_rag_focused_tests.py
- tests/test_rag_focused_tests.py
- docs/rag_autorunner.md if a small focused-test note is needed

Expected verification for next task:
- pytest tests/test_rag_golden_questions.py --basetemp=.tmp\pytest
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
- golden question fixture exists and is valid structured data.
- each fixture item has a question and expected source metadata.
- tests pass without optional external dependencies.
- focused test runner includes the test if it is reliable.
- no archive-owned files are touched.
