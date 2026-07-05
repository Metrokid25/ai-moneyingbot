# RAG Approved Memory Rule Candidate Draft

## Purpose

The approved memory rule candidate draft turns an approved memory export preview into a RAG-internal reviewer report. It helps a human inspect whether any approved memory might later become a rule candidate.

This is still not a rule export. Draft candidates are not confirmed trading rules.

## Relationship to the Export Preview

The 063 export preview reads `agent_reports/rag_research_memory_store.jsonl` and selects only approved memory records. This draft step reads a `rag-approved-memory-export-preview-*.json` report and reshapes those preview candidates into a separate JSON/Markdown draft report for human review.

The draft step is DB-only. It does not reread external sources, fetch current market data, access Naver Cafe, or enrich the memory with outside knowledge.

## Usage

```powershell
python scripts\draft_rag_approved_memory_rule_candidates.py --preview-file agent_reports\rag-approved-memory-export-preview-YYYYMMDD-HHMMSS.json
```

When `--preview-file` is omitted, the script uses the latest `agent_reports\rag-approved-memory-export-preview-*.json` file.

Useful options:

```powershell
python scripts\draft_rag_approved_memory_rule_candidates.py --limit 20
python scripts\draft_rag_approved_memory_rule_candidates.py --tag-filter risk_control --tag-filter db_only
python scripts\draft_rag_approved_memory_rule_candidates.py --category-filter risk_control
python scripts\draft_rag_approved_memory_rule_candidates.py --dry-run
```

Dry run prints the draft candidate count and does not write report files.

## Report Files

The draft report writes:

- `agent_reports/rag-approved-memory-rule-candidate-draft-YYYYMMDD-HHMMSS.json`
- `agent_reports/rag-approved-memory-rule-candidate-draft-YYYYMMDD-HHMMSS.md`

Each draft candidate includes:

- `draft_id`
- `draft_status`
- `source_memory_id`
- `question_id`
- `question`
- `answer`
- `evidence_strength`
- `source_refs`
- `used_sources`
- `tags`
- `source_promotion_status`
- `source_promotion_review`
- `suggested_export_category`
- `draft_rule_candidate_summary`
- `draft_review_note`

## Boundaries

- Trading Bot rules are not generated.
- Trading Bot files are not modified.
- No Trading Bot integration is performed.
- External news, current market conditions, and general economic knowledge are not added.
- Draft candidates are not confirmed trading rules.
- Human review is required before any later conversion step.
