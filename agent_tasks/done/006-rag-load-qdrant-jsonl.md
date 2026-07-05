# Connect chunk output to Qdrant load path

Context:
- 004 implemented archive export JSONL ingest.
- 005 connected normalized ingest output to the chunking pipeline.
- The next step is to connect chunk output to the vector index/Qdrant loading path safely.

Goals:
- Ensure chunks produced from normalized JSONL input can be loaded into Qdrant/vector index flow.
- Reuse existing scripts/load_qdrant_phase2.py and src/rag_qdrant.py where possible.
- Add or update a JSONL chunk input path if needed.
- Preserve metadata in Qdrant payload:
  article_id, content_hash, url/source URL, created_at, collected_at, source, title, chunk_id.
- Avoid archive.db writes.
- Avoid archive-owned crawler/parser/collector/browser code.
- Keep the implementation testable without requiring a live Qdrant server where possible.
- Prefer dry-run or fake/in-memory client tests if existing architecture supports it.

Allowed implementation files for next task:
- scripts/load_qdrant_phase2.py
- src/rag_qdrant.py
- src/rag_retrieval.py if metadata compatibility requires it
- tests/test_rag_qdrant.py
- tests/test_rag_retrieval.py if metadata compatibility requires it
- tests/fixtures/
- docs/rag_ingest_boundary.md if a small clarification is needed

Expected verification for next task:
- python scripts/load_qdrant_phase2.py --help
- pytest tests/test_rag_qdrant.py --basetemp=.tmp\pytest
- pytest tests/test_rag_retrieval.py --basetemp=.tmp\pytest if touched
- git status -sb
- git diff --stat

If qdrant_client is missing in the current environment:
- Do not install dependencies automatically.
- Keep focused tests skippable or mock/fake-based where appropriate.
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
- chunk JSONL output has a clear load path into Qdrant/vector index flow
- Qdrant payload preserves required article/chunk metadata
- focused tests pass or clearly skip only missing optional dependency cases
- no archive-owned files touched
