# RAG Trading Export Preview

## Purpose

The RAG trading export preview turns the RAG-internal approved rule candidate registry into a human-readable preview of what a later Trading Bot handoff could inspect. It is a review report only.

This preview is not a Trading Bot input file, not a Trading Bot rule, and not approval for live trading.

## Relationship to the Registry

Task 066 stores approved RAG rule candidates in `agent_reports/rag_rule_candidate_registry.jsonl`. This preview reads that RAG-internal registry and selects candidates whose `registry_status` is `registered_needs_final_review`.

Archived candidates are excluded by default. Use `--status-filter archived` only when a reviewer explicitly wants to inspect archived records.

## Boundaries

- DB-only: use only the RAG-internal registry JSONL and the DB-grounded fields already present in it.
- Do not use external news, current market conditions, or general economic knowledge to enrich preview records.
- Do not access Naver Cafe.
- Do not write `archive.db` or mutate raw `data/` originals.
- Trading Bot automatic application is prohibited.
- Trading Bot files are not created or modified.
- Trading Bot rules are not generated.
- Automated trading signals are not generated.
- The preview is not a Trading Bot connection export file.

## Usage

```powershell
python scripts\preview_rag_trading_rule_export.py
```

Useful options:

```powershell
python scripts\preview_rag_trading_rule_export.py --registry-file agent_reports\rag_rule_candidate_registry.jsonl
python scripts\preview_rag_trading_rule_export.py --category-filter risk_control --category-filter pattern
python scripts\preview_rag_trading_rule_export.py --status-filter archived
python scripts\preview_rag_trading_rule_export.py --limit 20
python scripts\preview_rag_trading_rule_export.py --dry-run
```

Dry run prints the preview candidate count and skip counts without writing JSON or Markdown reports.

## Report Files

The preview writes:

- `agent_reports/rag-trading-rule-export-preview-YYYYMMDD-HHMMSS.json`
- `agent_reports/rag-trading-rule-export-preview-YYYYMMDD-HHMMSS.md`

## Preview Record Schema

Each preview candidate includes:

- `preview_id`
- `registry_id`
- `source_rule_candidate_id`
- `rule_candidate_category`
- `registry_status`
- `export_preview_status`
- `rule_candidate_summary`
- `source_question`
- `source_answer`
- `evidence_strength`
- `source_refs`
- `used_sources`
- `tags`
- `schema_name`
- `schema_version`
- `boundary_notice`
- `trading_export_preview_note`

`export_preview_status` is always `preview_needs_human_review`.

## Not Done Here

- Trading Bot rule creation.
- Trading Bot file modification.
- Trading Bot connection export file generation.
- Automated trading signal generation.
- Live deployment approval.
