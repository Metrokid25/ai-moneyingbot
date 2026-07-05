# RAG Approved Memory Export Preview

## Purpose

The approved memory export preview collects only human-approved RAG research memory records and formats them for later reviewer inspection. It is a preview report for possible future rule-candidate discussion, not a rule export.

## Relationship to 061 and 062

The 061 memory store writes DB-only research memory to `agent_reports/rag_research_memory_store.jsonl`. These records are study notes backed by internal retrieval outputs.

The 062 promotion gate adds human review state to those memory records. A record can be pending, approved, or rejected. This preview reads the same memory store after that gate and selects only records with `promotion_status=approved` or `promotion_review.status=approved`.

## Why Approved Memory Only

Pending, rejected, and empty-status memory records have not been accepted by a human reviewer for this next review stage. Excluding them keeps the preview narrow and prevents unreviewed memory from being mistaken for a Trading Bot rule candidate.

Approved memory is still not a confirmed trading rule. Approval only means a reviewer accepted it as useful RAG research memory.

## Usage

```powershell
python scripts\preview_rag_approved_memory_export.py
```

Useful options:

```powershell
python scripts\preview_rag_approved_memory_export.py --memory-store-file agent_reports\rag_research_memory_store.jsonl --out-dir agent_reports --limit 20
python scripts\preview_rag_approved_memory_export.py --dry-run
python scripts\preview_rag_approved_memory_export.py --tag-filter risk_control --tag-filter db_only
```

Dry run prints the approved candidate count and does not write report files.

## Report Files

The preview writes:

- `agent_reports/rag-approved-memory-export-preview-YYYYMMDD-HHMMSS.json`
- `agent_reports/rag-approved-memory-export-preview-YYYYMMDD-HHMMSS.md`

Each report includes:

- `memory_store_file`
- `generated_at`
- `approved_count`
- `dry_run`
- DB-only boundary notice
- Trading Bot automatic application prohibition notice
- preview-only notice
- approved candidates with memory id, question id, question, answer, evidence strength, sources, tags, promotion review metadata, suggested category, and reviewer-facing summary

The suggested category is limited to `principle`, `pattern`, `risk_control`, `watch_condition`, or `unresolved`. It is not a rule classification.

## Not Done Here

- Trading Bot rules are not automatically generated.
- Trading Bot files are not modified.
- External news, current market conditions, and general economic knowledge are not added.
- Approved memory is not treated as a confirmed trading rule.
