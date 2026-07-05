# RAG Memory Promotion Gate

## Purpose

The promotion gate keeps the RAG research memory store as a study notebook until a human reviewer decides which notes are useful enough to trust. A memory record can be reviewed, approved, or rejected, but approval only updates the memory store status.

## Relationship to the 061 Memory Store

The 061 memory store writes DB-only research notes to `agent_reports/rag_research_memory_store.jsonl`. Those notes are not final knowledge and are not Trading Bot rule candidates by default. The promotion gate reads that JSONL file and prepares a review report for records that still need human judgment.

## Statuses

- `pending`: waiting for human review. Existing `pending_human_review` records and empty `promotion_status` values are treated as pending review candidates.
- `approved`: a reviewer accepted the memory as useful RAG research memory.
- `rejected`: a reviewer decided the memory should not be promoted.

Unapproved memory must not be used as confirmed knowledge.

## Create a Review Report

```powershell
python scripts\prepare_rag_memory_promotion_review.py
```

Useful options:

```powershell
python scripts\prepare_rag_memory_promotion_review.py --memory-store-file agent_reports\rag_research_memory_store.jsonl --out-dir agent_reports --limit 20
python scripts\prepare_rag_memory_promotion_review.py --dry-run
```

The report is written as:

- `agent_reports/rag-memory-promotion-review-YYYYMMDD-HHMMSS.json`
- `agent_reports/rag-memory-promotion-review-YYYYMMDD-HHMMSS.md`

Dry run prints the candidate count and does not write report files.

## Update Promotion Status

```powershell
python scripts\update_rag_memory_promotion_status.py --memory-id ragmem_example --status approved --reviewer reviewer-name --note "Approved for RAG use."
```

Allowed statuses are `pending`, `approved`, and `rejected`. The updater changes only the matching memory record in `rag_research_memory_store.jsonl` and writes `promotion_review` metadata with status, note, reviewer, and reviewed timestamp. Running the same update again is idempotent and does not append repeated notes.

## Boundaries

- DB-only: use only internal DB retrieval outputs, agent reports, fixtures, docs, and the memory store.
- Do not use external web search, latest news, current market data, or general economic knowledge to fill gaps.
- Do not access Naver Cafe.
- Do not write `archive.db`, mutate raw `data/` originals, or call Archive Bot write paths.
- Do not create, export, or modify Trading Bot rules.
- Approval does not create a Trading Bot rule candidate file.
- Memory that has not been approved by a human must not be treated as confirmed knowledge.
