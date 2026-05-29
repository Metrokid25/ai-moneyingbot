# Display RAG source metadata in answer output and web UI

Context:
- 004 implemented archive export JSONL ingest.
- 005 connected normalized ingest output to chunking.
- 006 connected chunk output to Qdrant/vector index loading.
- 007 preserved metadata through retrieval and answer context.
- The next step is to expose that metadata clearly in CLI answer output and RAG web UI.

Goals:
- Ensure answer output includes source metadata from answer context:
  title, url/source URL, source, article_id, created_at, collected_at, chunk_id.
- Update scripts/answer_question_phase2.py output formatting if needed.
- Update scripts/serve_rag_web.py so retrieved sources show title, URL, date/source metadata where available.
- Keep answer generation logic compatible with existing tests.
- Prefer small, focused UI/source formatting changes.
- Do not require live Qdrant where tests can use fake/mock data.
- Do not write archive.db.
- Do not modify archive-owned crawler/parser/collector/browser code.
- Do not access Naver Cafe.

Allowed implementation files for next task:
- scripts/answer_question_phase2.py
- scripts/serve_rag_web.py
- src/rag_answer_context.py
- src/rag_answering.py
- tests/test_rag_answer_context.py
- tests/test_rag_answering.py
- tests/test_rag_web.py
- tests/fixtures/
- docs/rag_ingest_boundary.md if a small clarification is needed

Expected verification for next task:
- python scripts/answer_question_phase2.py --help
- pytest tests/test_rag_answer_context.py --basetemp=.tmp\pytest
- pytest tests/test_rag_answering.py --basetemp=.tmp\pytest
- pytest tests/test_rag_web.py --basetemp=.tmp\pytest if touched
- git status -sb
- git diff --stat

If optional dependencies are missing in the current environment:
- Do not install dependencies automatically.
- Keep focused tests skippable or fake-based where appropriate.
- Report dependency limitation clearly.

Forbidden:
- git add .
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
- CLI answer output can show source metadata without losing title/url/date/source fields.
- Web UI source display includes title, URL/source URL, source/date metadata where available.
- Focused tests pass or clearly skip only missing optional dependency cases.
- No archive-owned files touched.
