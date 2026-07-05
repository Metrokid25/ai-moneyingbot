Title: Add RAG chunk quality report

Context:
- RAG chunking is now covered by fixture smoke tests.
- The next step is to add a read-only quality report for chunk records.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-side work and must not be implemented in this RAG Bot worktree.

Goals:
- Add a read-only report that checks RAG chunk quality.
- Detect empty chunks, too-short chunks, too-long chunks, missing metadata, and duplicate source candidates.
- Prefer fixture JSONL or temporary JSONL inputs for tests.
- Emit the report to stdout or a separate explicit output path.
- Keep the implementation testable without archive.db writes or raw data mutation.
- Add focused tests that can be included in scripts/run_rag_focused_tests.py if reliable.
- Do not perform archive collection or archive writes.
- Do not write archive.db.
- Do not modify data/ originals.
- Do not access Naver Cafe.
- Do not touch archive crawler/parser/collector/browser code.

Allowed implementation files for next task:
- scripts/report_rag_chunk_quality.py
- src/rag_chunking.py if a small reusable helper is needed
- tests/test_rag_chunk_quality_report.py
- tests/fixtures/
- scripts/run_rag_focused_tests.py
- tests/test_rag_focused_tests.py
- docs/rag_autorunner.md if a small focused-test note is needed

Expected verification for next task:
- python scripts/report_rag_chunk_quality.py --help
- pytest tests/test_rag_chunk_quality_report.py --basetemp=.tmp\pytest
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
- chunk quality report identifies empty/short/long chunks and metadata issues.
- report runs read-only on fixture or temporary JSONL data.
- tests pass without optional external dependencies.
- focused test runner includes the test if it is reliable.
- no archive-owned files are touched.
