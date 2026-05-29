# Preserve Qdrant metadata through retrieval and answer context

Context:
- 004 implemented archive export JSONL ingest.
- 005 connected normalized ingest output to chunking.
- 006 connected chunk output to Qdrant/vector index loading.
- The next step is to ensure metadata stored in Qdrant payload survives retrieval and answer context building.

Goals:
- Ensure retrieval results preserve chunk/article metadata:
  article_id, content_hash, url/source URL, created_at, collected_at, source, title, chunk_id.
- Ensure answer context exposes source metadata for answer generation.
- Ensure scripts/answer_question_phase2.py or src/rag_answer_context.py can display or pass through source URL/title/date metadata.
- Reuse existing src/rag_retrieval.py, src/rag_answer_context.py, and src/rag_answering.py where possible.
- Keep tests fake/mock based so a live Qdrant server is not required.
- Do not write archive.db.
- Do not modify archive-owned crawler/parser/collector/browser code.
- Do not access Naver Cafe.

Allowed implementation files for next task:
- src/rag_retrieval.py
- src/rag_answer_context.py
- src/rag_answering.py
- scripts/answer_question_phase2.py
- tests/test_rag_retrieval.py
- tests/test_rag_answer_context.py
- tests/test_rag_answering.py
- tests/fixtures/
- docs/rag_ingest_boundary.md if a small clarification is needed

Expected verification for next task:
- pytest tests/test_rag_retrieval.py --basetemp=.tmp\pytest
- pytest tests/test_rag_answer_context.py --basetemp=.tmp\pytest if exists or is added
- pytest tests/test_rag_answering.py --basetemp=.tmp\pytest if touched
- python scripts/answer_question_phase2.py --help
- git status -sb
- git diff --stat

If qdrant_client is missing in the current environment:
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
- retrieval result objects or dictionaries preserve required metadata
- answer context includes source URL/title/date/article metadata
- answer generation can pass through or display source metadata without losing it
- focused tests pass or clearly skip only missing optional dependency cases
- no archive-owned files touched
