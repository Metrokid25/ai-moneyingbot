# Connect RAG JSONL ingest output to chunking pipeline

Goals:
- Define how normalized records from scripts/ingest_archive_export.py feed the RAG chunking pipeline.
- Add or update a small script path that can take normalized ingest output and produce chunk-ready records if needed.
- Reuse existing src/rag_chunking.py behavior where possible.
- Preserve article_id, content_hash, url/source URL, created_at, collected_at in chunk metadata.
- Ensure no archive.db writes.
- Ensure no data/ original modification.
- Ensure no Naver Cafe access.
- Keep archive crawler/parser/collector code untouched.

Allowed implementation files for next task:
- scripts/ingest_archive_export.py
- scripts/build_chunks_phase2.py
- src/rag_chunking.py
- tests/test_rag_chunking.py
- tests/test_ingest_archive_export.py
- tests/fixtures/

Expected verification for next task:
- python scripts/ingest_archive_export.py --input tests/fixtures/sample_articles.jsonl --output .tmp/normalized_articles.jsonl --overwrite
- python scripts/build_chunks_phase2.py --help
- pytest tests/test_ingest_archive_export.py --basetemp=.tmp\pytest
- pytest tests/test_rag_chunking.py --basetemp=.tmp\pytest

Forbidden:
- git add .
- archive.db write/delete/reset
- .env modification
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
- normalized ingest output can be used as chunking input or clearly converted into chunk-ready records
- chunk metadata preserves article_id/content_hash/url/created_at/collected_at/source
- focused tests pass
- no archive-owned files touched
