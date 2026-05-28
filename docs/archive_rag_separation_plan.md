# Archive/RAG Separation Plan

## 1. Summary

This repository is named `naver_cafe_archive`, while the current remote/project identity is `ai-moneyingbot`. The codebase currently contains two distinct products in one flat Python namespace:

- Archive Bot: collects Naver Cafe article lists and bodies, stores canonical article records in SQLite, tracks retry/failure state, and now has a dry-run daily pipeline.
- RAG Bot: consumes archived article text, builds chunks and embeddings, loads/searches Qdrant, generates answers, evaluates retrieval, and serves a local web UI.

The safest operating model is:

- Archive Bot = raw article producer.
- RAG Bot = raw article consumer.
- Archive Bot may write `archive.db`.
- RAG Bot should read `archive.db` read-only and write only its own chunk/vector/index artifacts.

The main separation risk is the flat import layout (`from db import ...`, `from parser import ...`, `from rag_retrieval import ...`) plus shared `data/` conventions. Logical package boundaries should be introduced before any physical repo split.

## 2. Current Repository State

Initial state checked on this review:

- Working directory: `C:\projects\naver_cafe_archive`
- Branch state: `main...origin/main`
- Recent commit: `a29ac32 Add daily archive dry-run pipeline`
- Untracked helper file present: `scripts/_step3_verify_v2.py`

Runtime and local-only paths excluded from component classification:

- `.venv/`
- `.pytest_cache/`
- `.claude/`
- `.tmp/`
- `reports/`
- `state/`

Data paths considered only as data-flow inputs/outputs, not modified:

- `data/`
- `archive.db`
- root `archive.db` if present

## 3. Archive Components

| File | Role | Key Functions/Classes | Dependencies | Separation Notes |
|---|---|---|---|---|
| `src/main.py` | One-shot article archive entrypoint from a single Naver Cafe article URL. | `run` | `db`, `browser`, `parser`, `models` | Archive-only. Move under `src/archive/cli_one.py` or similar. It currently writes via `upsert_article`. |
| `src/indexer.py` | Naver Cafe list-page indexer that stores article metadata without body text. | `build_page_url`, `save_debug`, `run_indexer`, `_sleep`, `main` | `browser`, `config`, `db`, `models`, `parser`, Playwright | Archive-only. Depends on browser session, login, parser, and DB writes. Sleep/rate-limit behavior should remain archive-side. |
| `scripts/index_tail.py` | Tail-page detection, snapshot creation, and incremental list indexing after snapshot. | `_get_db_max_id`, `_create_snapshot`, `_load_latest_snapshot`, `_collect_after_snapshot`, `_fetch_rows`, `find_tail`, `index_pages`, `main` | `browser`, `db`, `indexer`, `models`, `parser` | Archive-only. Snapshot files currently live under `data/`; future state/snapshot ownership should be explicit under archive state. |
| `src/collector.py` | Article body collector with retry handling and transient/permanent failure handling. | `BlockReason`, `collect_body`, `_check_and_demote`, `_handle_transient`, `_save_diagnostic` | `browser`, `config`, `db`, `models`, `parser`, Playwright | Archive-only. Critical DB writer. Should not be imported by RAG. |
| `scripts/batch_recollect.py` | Batch body recollection for `INDEXED` articles with delay, simulation, logging, and circuit breaker. | `_CircuitBreaker`, `_build_sim_map`, `_open_logfile`, `_write_checkpoint`, `_write_final_report`, `main` | `browser`, `collector`, `db`, `models` | Archive-only. Contains operational safeguards. Keep outside RAG package. |
| `scripts/daily_archive.py` | Daily archive pipeline skeleton with dry-run mock mode, state file, failed queue, report generation, duplicate filtering. | `DailyStats`, `run_daily_archive`, `collect_new_articles`, `save_article`, `load_crawl_state`, `load_failed_queue`, `write_daily_report`, `main` | `db`, `models`, JSON/state/report paths | Archive-only. Currently real collection is not wired. Should become main scheduler entrypoint and later call archive list/body functions. |
| `src/browser.py` | Playwright browser/session/login/block-detection layer. | `BrowserSession`, `fetch_page`, `wait_for_login`, `check_blocked`, `_is_login_page` | `config`, Playwright | Archive-only infrastructure. Should be isolated from RAG to avoid accidental network/browser behavior. |
| `src/parser.py` | HTML parsing for Naver Cafe article IDs, article body, and article list rows. | `extract_article_id`, `parse_article`, `parse_article_list` | BeautifulSoup | Mostly archive-side. RAG should consume normalized article records, not raw Naver HTML. |
| `src/db.py` | SQLite article schema, migrations, CRUD, retry-state updates. | `get_conn`, `init_db`, `_migrate`, `article_exists`, `upsert_article`, `get_article_by_id`, `get_articles_by_status`, `update_article_body`, retry record functions | `config`, `models`, SQLite | Shared by current implementation, but write APIs should be archive-only. RAG should use read-only access or export files. |
| `src/models.py` | Article dataclass and status constants. | `Article`, `Status` | standard library | Shared schema today. Split into archive domain model plus export contract later. |
| `scripts/verify_collect_body.py` | Manual verification script for body collection. | `main` | `browser`, `collector`, `db`, `models` | Archive diagnostic. Keep out of RAG. |
| `scripts/verify_retry_columns.py` | Verifies retry-related DB columns and counts. | script-level checks | `config`, SQLite | Archive/DB diagnostic. Read-only intent, but tightly coupled to archive schema. |
| `scripts/verify_phase2_migration.py` | Verifies DB migration/schema/article lookup assumptions. | script-level checks | `config`, `db`, SQLite | Archive/schema diagnostic. Should live with archive DB maintenance docs. |
| `scripts/migrate_add_retry_columns.py` | DB migration for retry columns and backup. | migration script | `config`, SQLite, shutil | Archive DB maintenance. Destructive potential; keep separate from RAG package and never run from RAG flows. |
| `scripts/migrate_article_id_to_int.py` | DB migration for `article_id` integer conversion. | migration script | `config`, `db`, SQLite | Archive DB maintenance. Must remain explicit/manual. |
| `scripts/probe_dynamic_load.py` | One-off dynamic-load/browser diagnostic. | `_probe_article`, `_fetch_url_map`, `main` | `browser`, `db`, Playwright | Diagnostic helper, not core. Mention only if retained; do not include in packaged app. |
| `scripts/diag_article_url.py`, `scripts/diag_block_pattern.py`, `scripts/diag_dom_structure.py`, `scripts/diag_empty_body.py` | One-off archive diagnostics. | diagnostic `main` functions/helpers | `browser`, `db`, `config`, SQLite | Gitignored diagnostic scripts. Keep excluded from core separation plan unless promoted intentionally. |

## 4. RAG Components

| File | Role | Key Functions/Classes | Dependencies | Separation Notes |
|---|---|---|---|---|
| `src/rag_chunking.py` | Builds embedding text and chunk records from archived articles. | `build_embedding_text`, `parse_year_month`, `split_text_into_chunks`, `build_chunk_records` | standard library | RAG-only transformation layer. Input should become JSONL export records rather than direct DB rows. |
| `scripts/build_chunks_phase2.py` | Reads `archive.db` and writes chunk JSONL. | `fetch_articles`, `build_chunks`, `summarize`, `write_jsonl`, `main` | `rag_chunking`, SQLite, `data/archive.db` | RAG ingestion bridge today. It reads archive DB read-only via URI mode; good boundary candidate for replacement by JSONL import. |
| `scripts/embed_chunks_phase2.py` | Embeds chunk JSONL with Voyage or writes deterministic mock embeddings. | `read_chunks`, `read_done_chunk_ids`, `select_chunks`, `mock_embedding`, `write_mock_outputs`, `embed_with_voyage_execute`, `resolve_output_paths`, `main` | NumPy, Voyage, JSONL files | RAG-only artifact writer. Should write under RAG-owned `data/rag/` or `data/qdrant/`, not archive state. |
| `src/rag_qdrant.py` | Validates chunks/embeddings and builds/loads Qdrant points. | `load_chunks_jsonl`, `load_embeddings`, `load_ids`, `validate_qdrant_inputs`, `build_payload`, `build_point`, `ensure_collection_for_load`, `upsert_points` | `rag_chunking`, NumPy, Qdrant | RAG-only. Writes vector store only when explicitly executed. |
| `scripts/load_qdrant_phase2.py` | CLI for Qdrant collection creation/upsert from chunks and embeddings. | `load_inputs`, `build_summary`, `main` | `rag_qdrant`, Qdrant | RAG-only vector index writer. Must not write archive DB. |
| `src/rag_retrieval.py` | Query embedding, Qdrant search, retrieval formatting, eval JSONL helpers. | `validate_run_mode`, `validate_top_k`, `embed_query`, `open_qdrant_client`, `search_qdrant`, `format_search_results`, `build_eval_record`, `write_jsonl` | Qdrant, Voyage, NumPy, `.env` | RAG-only. Uses external APIs when executed; keep separate from archive scheduler. |
| `scripts/search_qdrant_phase2.py` | CLI for Qdrant search. | `build_summary`, `print_results`, `main` | `rag_retrieval` | RAG-only read/search entrypoint. |
| `src/rag_answer_context.py` | Formats retrieved points into answer context. | `truncate_text`, `build_context_item`, `build_context_items`, `format_context_markdown`, `format_context_json`, `write_text_output` | standard library | RAG-only. |
| `scripts/build_answer_context_phase2.py` | CLI to retrieve and write answer context without LLM answer generation. | `main` | `rag_answer_context`, `rag_retrieval` | RAG-only. Calls Voyage/Qdrant when executed. |
| `src/rag_answering.py` | RAG answer generation with OpenAI, cost estimation, answer formatting. | `LlmUsage`, `EstimatedCost`, `LlmResult`, `run_rag_answer`, `call_llm`, `build_answer_record`, `format_answer_markdown`, `format_answer_json` | `rag_answer_context`, `rag_retrieval`, OpenAI, `.env` | RAG-only. Should not depend on archive DB directly. |
| `scripts/answer_question_phase2.py` | CLI for full RAG answer generation. | `ensure_collection_ready`, `write_output`, `main` | `rag_answering`, `rag_retrieval` | RAG-only. |
| `scripts/serve_rag_web.py` | Local web UI and API for RAG answers, plus article page lookup. | `RagWebHandler`, `RagHTTPServer`, `run_server`, `run_rag_answer`, `open_archive_db_readonly`, `fetch_article`, `fetch_article_metadata`, `enrich_sources_with_article_metadata` | `rag_answering`, `rag_retrieval`, SQLite, Qdrant/OpenAI/Voyage transitively | RAG UI with read-only archive DB dependency. This is the strongest shared-boundary file: keep DB access read-only or replace with exported metadata lookup. |
| `scripts/evaluate_retrieval_phase2.py` | Evaluates retrieval from Qdrant for fixed queries. | `run_query`, `main` | `rag_retrieval` | RAG-only evaluation. |
| `scripts/evaluate_rag_retrieval_set.py` | Retrieval evaluation against JSONL questions. | `load_questions`, `evaluate_records`, `main` | JSONL, RAG retrieval outputs | RAG-only evaluation. |
| `scripts/evaluate_phase1.py` | Phase 1 retrieval metric calculation over embedding arrays and eval docs. | `cosine_similarity_matrix`, `main` | NumPy, JSON/Markdown files under `data`/`docs` | RAG-only legacy/evaluation. |
| `scripts/embed_corpus_phase1.py` | Phase 1 corpus embedding from `archive.db`. | `main` | SQLite, Voyage, NumPy | RAG ingestion bridge. Reads archive DB and writes embedding artifacts. Should be superseded by export/import boundary. |
| `scripts/embed_queries_phase1.py` | Phase 1 query embedding generation. | `main` | Voyage, NumPy | RAG-only evaluation artifact writer. |
| `scripts/diagnose_phase1.py` | Phase 1 retrieval diagnosis. | `main` | NumPy, SQLite, docs | RAG diagnostic. |
| `docs/phase2_design.md` | Existing Phase 2 design notes spanning DB, collector, chunking, Qdrant, and answer flow. | n/a | n/a | Cross-domain design doc. Future docs should distinguish archive source-of-truth from RAG derived artifacts. |
| `docs/rag_phase1_eval.md`, `docs/rag_phase1_diagnosis.md` | RAG evaluation/diagnostic reports. | n/a | n/a | RAG documentation/artifacts. |
| `tests/fixtures/rag_eval_questions.jsonl` | RAG evaluation fixture. | n/a | n/a | RAG test fixture. |

## 5. Shared Components

| Component | Current Use | Archive Use | RAG Use | Recommended Boundary |
|---|---|---|---|---|
| `src/db.py` / `archive.db` | Canonical `articles` table, schema migration, CRUD, retry state. | Writes article metadata/body/status/retry fields. | Reads articles for chunking and web source metadata; some scripts connect directly with SQLite. | Archive owns write APIs. RAG uses read-only DB connection or, preferably, exported JSONL. |
| `src/models.py` / `Article` / `Status` | Shared article dataclass and status constants. | Constructs records for DB writes and retry transitions. | Used in tests and occasionally status filtering concepts. | Keep archive domain model internal. Define a stable export schema for RAG (`article_id`, `title`, `posted_at`, `author`, `clean_text`, `url`, `status`). |
| `src/config.py` | Loads `.env`, defines `PROJECT_ROOT`, `DATA_DIR`, `DEBUG_DIR`, `DB_PATH`, browser settings. | Browser and DB paths/settings. | Some RAG scripts use their own paths; DB verification scripts use `DB_PATH`; RAG modules load `.env` separately. | Split into `archive.config` and `rag.config` or a small shared path utility with no side effects beyond path constants. |
| `data/` | Mixed source DB and derived RAG artifacts. | `data/archive.db`, snapshots, debug-related generated data. | chunks JSONL, embeddings `.npy`, Qdrant local store, eval outputs. | Separate subtrees: `data/archive/` for source/state exports and `data/rag/` or `data/vector/` for derived artifacts. Keep `archive.db` source-owned. |
| `article_id` | Primary key and join key across all flows. | Dedupe, DB primary key, retry target, source URL identity. | Chunk IDs use `{article_id}:{chunk_index}`, web UI maps results back to source metadata. | Treat as stable cross-boundary identifier in export contract. Keep type integer. |
| `url` / source page URL | Original Naver Cafe article URL and list source page. | Used for collection/navigation and stored in DB. | Web UI shows source links; chunks may include source metadata. | Export only safe metadata; RAG should not navigate source URLs. |
| `posted_at`, `saved_at`, `updated_at`, daily state timestamps | Article and run timing metadata. | Collection status, reporting, retries, future incremental collection. | Chunk metadata year/month and search filters. | Export `posted_at` plus optional `collected_at`/`updated_at`; avoid RAG writing collection timestamps. |
| `tests` path setup | Tests insert `src` or `scripts` into `sys.path` and import flat modules. | Archive tests import `db`, `collector`, `index_tail`, `daily_archive`. | RAG tests import `rag_*` and scripts directly. | Tests should move with packages after logical separation; avoid global `sys.path` collisions. |
| CLI scripts under `scripts/` | All entrypoints are mixed in one directory. | Archive collection, verification, migration, daily run. | RAG build, embed, load, search, answer, eval, web UI. | Keep scripts but make names explicit: `daily_archive.py`, `export_archive_articles.py`, `ingest_archive_export.py`, `answer_question_phase2.py`; internally import namespaced packages. |
| `.env` | Holds external API/browser/env settings. | Browser settings, possibly future archive settings. | `VOYAGE_API_KEY`, `OPENAI_API_KEY`, model execution settings. | Do not share secrets across bots by default. Use explicit env variable groups and never load API keys in archive dry-run. |

## 6. Data Flow

Current inferred data flow:

```text
Naver Cafe
  -> archive browser/list/body collection
  -> parser
  -> db.upsert/update retry state
  -> data/archive.db
```

```text
data/archive.db
  -> RAG chunk build scripts
  -> data/chunks_phase2.jsonl
  -> embedding scripts
  -> data/embeddings_phase2*.npy and ids/progress files
  -> Qdrant local vector index under data/qdrant
```

```text
Qdrant/vector index
  -> retrieval
  -> answer context
  -> answer generation
  -> CLI output or local web UI
  -> optional read-only archive.db lookup for source metadata/article page display
```

Recommended ownership:

- Archive Bot is the source-of-truth producer.
- RAG Bot is a derived-data consumer.
- Archive Bot can write `archive.db`.
- RAG Bot reads `archive.db` read-only only during the transition.
- RAG Bot writes its own chunk, embedding, progress, and vector-store artifacts.
- Long-term, RAG should ingest an archive export instead of connecting to the archive DB directly.

## 7. Import and Packaging Risks

Current risks:

- Flat imports couple unrelated domains:
  - `from db import init_db, upsert_article, article_exists`
  - `from parser import extract_article_id, parse_article`
  - `from browser import BrowserSession`
  - `from collector import collect_body`
  - `from rag_retrieval import search_qdrant`
  - `from rag_answering import run_rag_answer`
- Many scripts mutate `sys.path` to include `src`, making package boundaries implicit and order-dependent.
- `parser.py` is archive-specific but its generic name is easy to confuse with non-archive parsing.
- `db.py` exposes both read and write functions in one module, so RAG code can accidentally import write-capable APIs.
- `data/` contains both source data (`archive.db`) and derived RAG artifacts (chunks, embeddings, Qdrant).
- RAG web UI correctly uses `open_archive_db_readonly`, but it still depends directly on archive DB schema.
- Diagnostic and migration scripts sit next to product CLIs, increasing accidental execution risk.
- `scripts/_step3_verify_v2.py` is currently an untracked helper file; leave it unmodified and do not treat it as a stable component.

Recommended future import shape:

```python
from src.archive.parser import parse_article
from src.archive.db import upsert_article
from src.rag.retrieval import search_qdrant
from src.rag.answering import run_rag_answer
```

Preferred boundary after Phase 2:

```python
from src.archive.export import write_article_export
from src.rag.ingest import ingest_article_export
```

## 8. Test Classification

| Test File | Category | Notes |
|---|---|---|
| `tests/test_daily_archive.py` | Archive tests | Daily dry-run pipeline, crawl state, failed queue, report generation, duplicate handling. |
| `tests/test_parser.py` | Archive tests | Tests `parse_article`; parser is Naver Cafe archive-specific. |
| `tests/test_retry_logic.py` | Archive tests | DB retry columns and `collect_body` behavior with mocked browser/parser. |
| `tests/test_snapshot.py` | Archive tests | `index_tail` snapshot and incremental list indexing behavior. |
| `tests/test_circuit_breaker.py` | Archive tests | Batch recollect circuit breaker. |
| `tests/test_rag_chunking.py` | RAG tests | Chunking, metadata, embedding text generation. |
| `tests/test_embed_chunks_phase2.py` | RAG tests | Chunk JSONL read, duplicate detection, mock embeddings, dry-run behavior. |
| `tests/test_rag_qdrant.py` | RAG tests | Qdrant input validation, point/payload construction, CLI behavior. |
| `tests/test_rag_retrieval.py` | RAG tests | Query validation, vector validation, Qdrant search formatting. |
| `tests/test_retrieval_eval.py` | RAG tests | Retrieval eval record/output helpers. |
| `tests/test_rag_retrieval_eval_set.py` | RAG tests | Eval question set loading/evaluation behavior. |
| `tests/test_rag_eval_questions.py` | RAG tests | Eval fixture validation. |
| `tests/test_rag_answer_context.py` | RAG tests | Context truncation, formatting, output path handling. |
| `tests/test_rag_answering.py` | RAG tests | Answer prompt, LLM response parsing, cost estimate, answer CLI behavior. |
| `tests/test_rag_web.py` | RAG tests with shared read-only archive DB | Web UI answer endpoint and local article page rendering; depends on archive DB schema read-only. |
| `tests/__init__.py` | Shared/system tests | Test package marker only. |

## 9. Phase 1: Logical Separation in Same Repo

Goal: keep one repository, but make ownership and import boundaries explicit.

Recommended target structure:

```text
src/
  archive/
    browser.py
    collector.py
    db.py
    indexer.py
    models.py
    parser.py
  rag/
    chunking.py
    qdrant_store.py
    retrieval.py
    answer_context.py
    answering.py
scripts/
  daily_archive.py
  export_archive_articles.py
  ingest_archive_to_rag.py
  answer_question_phase2.py
```

Rules for Phase 1:

- Do not split the repository yet.
- Do not move all code in one large change.
- One work unit should change only one import boundary at a time.
- Run focused tests after each small move, then full tests before commit.
- Do not let concurrent Codex agents edit archive and RAG package paths at the same time.
- Keep compatibility wrappers temporarily if needed, for example `src/parser.py` importing from `src.archive.parser`, but retire wrappers after scripts/tests are migrated.
- Explicitly mark RAG access to `archive.db` as read-only.

Suggested Phase 1 sequence:

1. Create package directories and empty `__init__.py` files.
2. Move RAG pure modules first (`rag_chunking`, `rag_qdrant`, `rag_retrieval`, `rag_answer_context`, `rag_answering`) because they are less coupled to browser/DB writes.
3. Update RAG scripts/tests to namespaced imports.
4. Move archive modules (`browser`, `parser`, `models`, `db`, `collector`, `indexer`) with compatibility wrappers.
5. Update archive scripts/tests.
6. Document script ownership in README or a dedicated operations doc in a later documentation-only change.

## 10. Phase 2: Export/Import Boundary

Goal: reduce direct RAG dependency on archive DB.

Archive exports normalized article records:

```powershell
python scripts/export_archive_articles.py --since 2026-05-28 --out exports/articles_2026-05-28.jsonl
```

RAG imports export records into its own chunk/index flow:

```powershell
python scripts/ingest_archive_export.py --input exports/articles_2026-05-28.jsonl
```

Recommended JSONL article contract:

```json
{
  "schema_version": 1,
  "article_id": 169913,
  "title": "...",
  "url": "https://...",
  "author": "...",
  "posted_at": "2026.05.28.",
  "clean_text": "...",
  "status": "BODY_COLLECTED",
  "collected_at": "2026-05-28T00:00:00+09:00",
  "source": "naver_cafe_119investment_goodmorning"
}
```

Phase 2 rules:

- Archive export reads archive DB and writes appendable/exportable JSONL.
- RAG import reads JSONL and writes chunks/embeddings/vector index.
- RAG no longer needs archive DB for ingestion.
- Web UI may temporarily read archive DB for article page display, but should eventually use exported metadata or a RAG-side source metadata store.
- Exports should be immutable once published. Corrections should use a new export file or a record-level `updated_at`.

## 11. Phase 3: Optional Repo Split

Goal: decide whether physical repository separation is worth the maintenance overhead after the export/import contract is stable.

Possible future layout:

```text
C:\projects\naver_cafe_archive
C:\projects\ai-moneyingbot
```

Split criteria:

- Archive can run daily without importing RAG modules.
- RAG can rebuild/search/answer from export files without importing archive modules.
- JSONL contract has tests and sample fixtures.
- Operational ownership is clear: archive schedules and credentials are separate from RAG API keys/vector stores.
- Release process for export schema changes exists.

If split happens:

- Keep export/import contract versioned.
- Keep sample export fixtures in the RAG repo.
- Keep archive DB migrations only in the archive repo.
- Keep vector index/retrieval/answering only in the RAG repo.

## 12. Recommended Next Tasks

1. Connect real daily archive collection behind `scripts/daily_archive.py` using existing `index_tail`, `collector`, DB dedupe, state, failed queue, and conservative delay/circuit-breaker behavior.
2. Design the archive-to-RAG ingest boundary in detail: which fields RAG needs, read-only guarantees, freshness semantics, and failure handling.
3. Design and test the JSONL export/import contract with schema versioning and small fixtures.
4. Add a read-only archive DB adapter for RAG ingestion as an interim layer, so RAG code stops importing write-capable `db.py`.
5. Plan the package namespace migration in small PR-sized changes, starting with pure RAG modules and compatibility wrappers.

## 13. Open Questions

- Should `archive.db` remain at `data/archive.db`, or should archive-owned state move to `data/archive/archive.db` in a later migration?
- Does the RAG web UI need full article body rendering long-term, or only source metadata and snippets?
- How should deletes/blocked/private articles be represented in the export contract?
- Should failed archive items be exported to RAG as metadata, or should RAG ingest only `BODY_COLLECTED` records?
- What is the expected freshness SLA between daily archive collection and RAG index refresh?
- Should Phase 1 include compatibility wrappers, or is a single synchronized import migration acceptable after tests are strong enough?
