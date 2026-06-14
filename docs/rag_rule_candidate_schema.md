# RAG Rule Candidate Draft Schema

## Purpose

The RAG rule candidate draft schema freezes the JSON shape used for human review of RAG-internal rule candidate drafts. It makes the 064 draft reports reusable by defining required fields, allowed status values, allowed categories, safety boundary text, and validation behavior.

## Relationship to 064 Drafts

Task 064 generates `rag-approved-memory-rule-candidate-draft-YYYYMMDD-HHMMSS.json` and `.md` reports from approved memory export preview reports. This schema describes that draft report format.

The generator emits:

- `schema_name: rag_rule_candidate_draft`
- `schema_version: 1`
- `candidate_count`
- `candidates`

Legacy 064 aliases such as `draft_count` and `draft_candidates` may remain for compatibility, but the canonical schema fields are `candidate_count` and `candidates`.

## Scope

This is a RAG-internal review schema. It is not a Trading Bot rule schema and it is not a rule export. A candidate that passes validation is still a draft for human review, not a confirmed trading rule.

## Boundaries

- DB-only: use only internal approved memory export preview reports and the DB-grounded memory text already present in those reports.
- Do not use external news, current market conditions, or general economic knowledge to enrich candidates.
- Do not access Naver Cafe.
- Do not write `archive.db` or mutate raw `data/` originals.
- Trading Bot automatic application is prohibited.
- Trading Bot rules are not generated.
- Trading Bot files are not modified.
- Automated trading signals are not generated.
- Rule registry entries are not saved without later human approval.

## Required Top-Level Fields

- `schema_name`
- `schema_version`
- `generated_at`
- `preview_file`
- `candidate_count`
- `candidates`
- `db_only_notice`
- `trading_boundary_notice`
- `draft_only_notice`

The boundary notices must state the DB-only principle, Trading Bot automatic application prohibition, and that drafts are not final rules.

## Required Candidate Fields

- `candidate_id`
- `rule_candidate_id`
- `source_memory_id`
- `draft_status`
- `rule_candidate_category`
- `suggested_export_category`
- `draft_summary`
- `rule_candidate_summary`
- `draft_rule_candidate_summary`
- `source_question`
- `question`
- `source_answer`
- `answer`
- `evidence_strength`
- `source_refs`
- `used_sources`
- `tags`
- `boundary_notice`

## Allowed Status Values

- `draft_needs_human_review`
- `rejected`
- `approved_for_registry`

The generator must default to `draft_needs_human_review`. It must not automatically create `approved_for_registry`.

## Allowed Category Values

- `principle`
- `pattern`
- `risk_control`
- `watch_condition`
- `unresolved`

## Validation

Run:

```powershell
python scripts\validate_rag_rule_candidate_drafts.py --draft-file agent_reports\rag-approved-memory-rule-candidate-draft-YYYYMMDD-HHMMSS.json
```

When `--draft-file` is omitted, the validator looks for the latest RAG rule candidate draft JSON in `agent_reports`.

The validator checks required top-level fields, required candidate fields, allowed status values, allowed categories, boundary notices, and candidate count consistency. It exits `0` when valid and non-zero when validation fails. It can print text or JSON summaries and can write a validation summary JSON with `--out-file`.

## Not Done Here

- Trading Bot rule creation.
- Trading Bot file modification.
- Automated trading signal generation.
- Rule registry storage without approval.
