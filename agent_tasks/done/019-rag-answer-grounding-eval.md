Title: Add RAG answer grounding eval

Context:
- RAG answer output now has citation and no-context contract tests.
- The next step is to verify answers remain grounded in provided source/context evidence.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-side work and must not be implemented in this RAG Bot worktree.

Goals:
- Add a focused grounding eval or contract test for RAG answer output.
- Verify answer output stays tied to provided fixture context and source/citation metadata.
- Prevent unsupported assertions, ungrounded conclusions, or answers without citations.
- Keep the design compatible with the existing citation contract and no-context contract.
- Avoid external LLM/API calls by using deterministic fake answer output or existing formatting boundaries.
- Avoid live vector DB usage and qdrant_client requirements.
- Add focused tests that can be included in scripts/run_rag_focused_tests.py if reliable.
- Do not write archive.db.
- Do not modify data/ originals.
- Do not access Naver Cafe.
- Do not touch archive crawler/parser/collector/browser code.

Allowed implementation files for next task:
- src/rag_answering.py
- src/rag_answer_context.py
- tests/test_rag_answer_grounding_eval.py
- tests/fixtures/
- scripts/run_rag_focused_tests.py
- tests/test_rag_focused_tests.py
- docs/rag_autorunner.md if a small focused-test note is needed

Expected verification for next task:
- pytest tests/test_rag_answer_grounding_eval.py --basetemp=.tmp\pytest
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
- grounding eval verifies answer/source/context relationships.
- unsupported answer output fails clearly.
- tests pass without optional external dependencies.
- focused test runner includes the test if it is reliable.
- no archive-owned files are touched.
