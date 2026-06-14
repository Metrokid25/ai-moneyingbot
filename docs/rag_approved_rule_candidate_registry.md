# RAG Approved Rule Candidate Registry

## Purpose

The RAG approved rule candidate registry stores only human-approved RAG rule candidate drafts for later RAG-internal review. It is a durable review backlog, not a Trading Bot rule registry.

## Relationship to 064 and 065

Task 064 creates RAG-internal rule candidate draft JSON/Markdown reports from approved memory export previews.

Task 065 freezes the draft schema and provides `scripts/validate_rag_rule_candidate_drafts.py`.

Task 066 reads a validated draft report and appends only candidates with `draft_status=approved_for_registry` to `agent_reports/rag_rule_candidate_registry.jsonl`.

## Scope

The registry is RAG-internal. It is not a Trading Bot rule export and it does not approve live trading behavior.

Only `approved_for_registry` candidates are stored. Candidates with `draft_needs_human_review`, `rejected`, empty status, or unknown status are excluded by default.

`approved_for_registry` means approved for RAG registry storage only. It is not approval for real trading, automated trading, or Trading Bot application.

## Boundaries

- DB-only: use only validated RAG rule candidate draft reports and the DB-grounded text already present in those reports.
- Do not use external news, current market conditions, or general economic knowledge to enrich registry records.
- Do not access Naver Cafe.
- Do not write `archive.db` or mutate raw `data/` originals.
- Trading Bot automatic application is prohibited.
- Trading Bot files are not created or modified.
- Trading Bot rules are not generated.

## Registry Record Schema

Each JSONL row includes:

- `registry_id`
- `created_at`
- `updated_at`
- `source_draft_file`
- `source_rule_candidate_id`
- `candidate_id`
- `rule_candidate_id`
- `source_memory_id`
- `rule_candidate_category`
- `draft_status`
- `registry_status`
- `rule_candidate_summary`
- `source_question`
- `source_answer`
- `evidence_strength`
- `source_refs`
- `used_sources`
- `tags`
- `boundary_notice`
- `schema_name`
- `schema_version`

Allowed `registry_status` values are:

- `registered_needs_final_review`
- `archived`

Newly stored `approved_for_registry` candidates use `registered_needs_final_review`.

## Idempotency

The updater reads the existing registry JSONL before appending. It prevents duplicates by `registry_id` and `source_rule_candidate_id`.

`registry_id` is a stable hash based on the source rule candidate id. Running the same draft file more than once does not increase the row count.

## Usage

```powershell
python scripts\update_rag_rule_candidate_registry.py --draft-file agent_reports\rag-approved-memory-rule-candidate-draft-YYYYMMDD-HHMMSS.json
```

When `--draft-file` is omitted, the updater uses the latest RAG rule candidate draft JSON in `agent_reports`.

Useful options:

```powershell
python scripts\update_rag_rule_candidate_registry.py --dry-run
python scripts\update_rag_rule_candidate_registry.py --registry-file agent_reports\rag_rule_candidate_registry.jsonl
python scripts\update_rag_rule_candidate_registry.py --out-dir agent_reports
```

Dry run validates the draft and prints counts without writing the registry file or summary report files.

## Summary Reports

Successful non-dry-run updates write:

- `agent_reports/rag-rule-candidate-registry-update-YYYYMMDD-HHMMSS.json`
- `agent_reports/rag-rule-candidate-registry-update-YYYYMMDD-HHMMSS.md`

The summary includes added count, duplicate skips, not-approved skips, stored registry ids, DB-only boundary text, Trading Bot boundary text, and registry-not-final-rule boundary text.

## Not Done Here

- Trading Bot rule creation.
- Trading Bot file modification.
- Automated trading signal generation.
- Trading Bot connection export file generation.
