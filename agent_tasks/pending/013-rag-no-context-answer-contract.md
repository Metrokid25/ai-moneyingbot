Title: Add RAG no-context answer contract test

Context:
- 009 added the RAG focused test runner.
- 010 added fixture JSONL smoke coverage for the RAG ingest -> chunking -> retrieval-ready boundary.
- 011 added fixture retrieval eval coverage for expected source metadata.
- 012 added an answer citation contract test for preserving source metadata into answer output.
- The next step is to verify no-context answer behavior when retrieval returns no usable evidence.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-side work and must not be implemented in this RAG Bot worktree.

Goals:
- Add a small contract test for RAG answer output when retrieval results are empty or evidence context is blank.
- Use only fixture data or pytest tmp_path-based temporary data.
- Avoid external LLM/API calls.
- Avoid a live vector DB and avoid qdrant_client as a required dependency.
- Verify that empty retrieval/context does not produce unsupported economic interpretation, unsupported conclusions, or fabricated citations.
- Prefer the most stable answer payload, CLI, or web boundary currently available in the code.
- Ensure the output includes the strongest available no-context signal, such as:
  no_context, insufficient_context, empty sources, empty citations, or a user-visible "no related evidence" style message.
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
- tests/test_rag_no_context_answer_contract.py
- tests/fixtures/
- scripts/run_rag_focused_tests.py
- tests/test_rag_focused_tests.py
- docs/rag_autorunner.md if a small focused-test note is needed

Expected verification for next task:
- pytest tests/test_rag_no_context_answer_contract.py --basetemp=.tmp\pytest
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
- empty retrieval/context fixture is prepared without archive.db, data originals, Naver Cafe, external APIs, or live vector DB.
- answer output is generated through a stable RAG answer boundary.
- output does not contain unsupported interpretation or fabricated evidence.
- source/citation output is empty or clearly marked as no-context/insufficient-context.
- python scripts/run_rag_focused_tests.py passes.
- no archive-owned files are touched.
