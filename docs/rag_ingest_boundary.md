# RAG Ingest Boundary

## Goal

Archive Bot is the producer of source articles.
RAG Bot is the consumer of source articles.

## Ownership

### Archive Bot owns
- crawling
- login/session/browser handling
- parsing raw Naver Cafe pages
- archive.db writes
- failed_queue for crawling
- daily archive reports

### RAG Bot owns
- chunking
- embedding
- vector index writes
- retrieval
- answer generation
- RAG eval
- RAG web UI

## Boundary Rule

RAG must not write to archive.db.
RAG may read archive data through a read-only adapter or JSONL export.

## Activation (2026-06-25)

Read-only consumption of the Archive Bot DB is now ACTIVATED by operator decision.

- RAG indexing reads the Archive Bot database at `C:\projects\naver_cafe_archive\data\archive.db` in read-only mode (`sqlite ?mode=ro`).
- Derived artifacts (chunks, embeddings, qdrant) are written only under this project's `data/` (gitignored).
- Still forbidden: writing to / mutating archive.db, modifying Archive Bot files, and committing `data/`.
- The JSONL export contract below remains the preferred long-term boundary; the direct read-only DB read is the current interim method until the export pipeline exists.

## Preferred Data Contract

Long-term preferred boundary:

Archive Bot:
archive.db → exports/articles_YYYY-MM-DD.jsonl

RAG Bot:
exports/articles_YYYY-MM-DD.jsonl → chunk → embedding → vector index

## JSONL Article Contract

Each line should be a JSON object.

Required fields:
- article_id
- title
- body_text
- url
- author
- created_at
- collected_at
- source
- content_hash

Optional fields:
- board_name
- comments
- attachments
- raw_html_path
- tags

## RAG Import Rules

- skip duplicate article_id/content_hash
- preserve article_id from the archive export
- preserve content_hash from the archive export
- preserve url/source URL from the archive export
- preserve created_at and collected_at from the archive export
- never mutate archive source records
- write only RAG-owned chunk/index/metadata outputs

## Future Commands

Archive export:

python scripts/export_archive_articles.py --since 2026-05-28 --out exports/articles_2026-05-28.jsonl

RAG import:

python scripts/ingest_archive_export.py --input exports/articles_2026-05-28.jsonl

## Risks

- shared src/db.py write-capable APIs
- flat imports
- ambiguous data/ ownership
- archive.db locking if read/write overlaps

## Recommended Safeguards

- read-only adapter for RAG
- JSONL boundary before repo split
- no direct archive write from RAG scripts
- tests that prove RAG import does not mutate archive.db
