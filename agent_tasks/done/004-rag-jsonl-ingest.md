# Implement RAG JSONL archive export ingest

Goals:
- Add scripts/ingest_archive_export.py
- Add tests/fixtures/sample_articles.jsonl
- Add tests/test_ingest_archive_export.py
- Load newline-delimited JSON articles from a provided --input path
- Validate required fields:
  article_id, title, body_text, url, author, created_at, collected_at, source, content_hash
- Skip duplicate article_id
- Skip duplicate content_hash
- Preserve article_id, content_hash, url/source URL, created_at, collected_at
- Prepare normalized records suitable for chunking
- Support --dry-run
- Do not write archive.db
- Do not modify data/ originals
- Do not access Naver Cafe
- Do not touch archive crawling/write code

Allowed files for the implementation:
- scripts/ingest_archive_export.py
- tests/fixtures/sample_articles.jsonl
- tests/test_ingest_archive_export.py
- docs/rag_ingest_boundary.md if small clarification is needed

Verification:
- python scripts/ingest_archive_export.py --help
- python scripts/ingest_archive_export.py --input tests/fixtures/sample_articles.jsonl --dry-run
- pytest tests/test_ingest_archive_export.py --basetemp=.tmp\pytest
- git status -sb
- git diff --stat

Forbidden:
- git add .
- .env
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
- ingest script exists and has --help
- dry-run works on sample fixture
- missing required fields produce clear error
- duplicate article_id/content_hash are skipped
- URL and metadata are preserved
- tests pass

## Completion note

Completed by:
- 203bc17 RAG autorunner: 20260529-101300

Verified:
- python scripts/ingest_archive_export.py --help
- python scripts/ingest_archive_export.py --input tests/fixtures/sample_articles.jsonl --dry-run
- pytest tests/test_ingest_archive_export.py --basetemp=.tmp\pytest
