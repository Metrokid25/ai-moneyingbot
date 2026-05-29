Title: Add RAG answer citation contract test

Context:
- 009 added the RAG focused test runner.
- 010 added fixture JSONL smoke coverage for ingest, chunking, and retrieval-ready output.
- 011 added fixture retrieval eval coverage that preserves source metadata through retrieval-ready results.
- The next step is to verify that retrieval source metadata survives into final answer output or answer payload structures.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-side work and must not be implemented in this RAG Bot worktree.

Goals:
- Add a small contract test for RAG answer output citation/source metadata.
- Use only fixture data or pytest tmp_path-based temporary data.
- Avoid external LLM/API calls.
- Verify that source metadata from retrieval results is preserved into answer output, answer payload, or the most stable answer/context boundary currently available.
- Check the available metadata fields where supported:
  source_id, title, url, source_path, chunk_id.
- Verify that source/citation display is not omitted from the answer body or answer payload.
- Prefer the most stable boundary between web UI output and CLI/answer function output in the current code structure.
- Keep the test independent of qdrant_client and other optional external dependencies.
- Include the new test in scripts/run_rag_focused_tests.py if it is reliable and RAG-only.
- Do not write archive.db.
- Do not modify data/ originals.
- Do not access Naver Cafe.
- Do not touch archive crawler/parser/collector/browser code.

Allowed implementation files for next task:
- src/rag_answer_context.py
- src/rag_answering.py
- scripts/answer_question_phase2.py if CLI formatting is the stable boundary
- scripts/serve_rag_web.py if web output is the stable boundary
- tests/test_rag_answer_context.py
- tests/test_rag_answering.py
- tests/test_rag_web.py
- tests/test_rag_answer_citation_contract.py
- tests/fixtures/
- scripts/run_rag_focused_tests.py
- tests/test_rag_focused_tests.py
- docs/rag_autorunner.md if a small focused-test note is needed

Expected verification for next task:
- pytest tests/test_rag_answer_citation_contract.py --basetemp=.tmp\pytest
- pytest tests/test_rag_answering.py --basetemp=.tmp\pytest if touched
- pytest tests/test_rag_answer_context.py --basetemp=.tmp\pytest if touched or added
- pytest tests/test_rag_web.py --basetemp=.tmp\pytest if touched
- python scripts/run_rag_focused_tests.py
- git status -sb
- git diff --stat

If optional dependencies are missing in the current environment:
- Do not install dependencies automatically.
- Keep focused tests fake-based or skip only optional dependency cases where appropriate.
- Report dependency limitations clearly.

Forbidden:
- git add .
- agent_tasks/pending/001-real-daily-archive-wiring.md
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
- fixture retrieval/context is prepared without archive.db, data originals, Naver Cafe, external APIs, or live vector DB.
- answer output or answer payload is generated through a stable RAG answer boundary.
- source metadata/citation fields are present and not silently dropped.
- python scripts/run_rag_focused_tests.py passes.
- no archive-owned files are touched.
