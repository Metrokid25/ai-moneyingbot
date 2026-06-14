# RAG End-to-End Runtime Smoke

## Purpose

The RAG end-to-end runtime smoke verifies that the 061 through 067 RAG pipeline artifacts can feed the next step at runtime. It is a fixture-based connectivity check, not a documentation-only graduation test and not a production pipeline run.

The smoke confirms this flow:

1. Create synthetic learning-loop and answer JSONL fixtures.
2. Store eligible answer records in a temporary RAG research memory store.
3. Promote the stored memory record to `approved`.
4. Build an approved memory export preview.
5. Draft RAG-internal rule candidates from that preview.
6. Validate the frozen rule candidate draft schema.
7. Copy the draft inside the smoke work directory and mark the copied candidate `approved_for_registry`.
8. Store only the approved candidate in a temporary RAG-internal registry.
9. Build the Trading handoff preview report from the temporary registry.
10. Verify the final JSON/MD preview artifacts and boundary notices.

## Boundaries

The smoke does not touch the real Qdrant collection, real `archive.db`, real Naver Cafe, real Trading Bot files, or production RAG memory and registry files. Every input and output path is explicitly placed under the smoke work directory.

The smoke is DB-only in the RAG sense: it uses synthetic fixture text and existing local RAG scripts only. It must not use external web search, current market news, general economic knowledge, Naver Cafe access, archive writes, or `archive.db`/raw `data/` mutations.

Trading Bot automatic application is prohibited. The final preview is not a Trading Bot input file, not a rule export, and not a trading signal.

## Running

Run with an explicit temporary work directory:

```powershell
.\.venv\Scripts\python.exe scripts\run_rag_end_to_end_runtime_smoke.py --work-dir .tmp/rag_e2e_runtime_smoke_manual
```

The default work directory is `.tmp/rag_e2e_runtime_smoke/<timestamp>`.

Use `--keep-artifacts` to reuse an existing work directory without clearing it first. Use `--timestamp` for deterministic report names in tests.

## Work-Dir Safety

The smoke work directory must be a safe temporary directory. Repository-internal work directories are accepted only under `.tmp/rag_e2e_runtime_smoke/` or another `.tmp/rag_e2e_runtime_smoke*` smoke-specific path. Existing external directories are accepted only under the system temp smoke directory. A new explicit external path may be created, but existing arbitrary external directories are rejected before cleanup.

The runner rejects the repository root and protected repository paths, including `agent_reports`, `data`, `scripts`, `tests`, `docs`, `src`, `.git`, and `.venv`. It also rejects paths under those directories. This applies even when `--keep-artifacts` is used; that option only disables cleanup and does not make an unsafe work directory valid.

Unsafe work directories fail with a non-zero exit before cleanup. The runner must not delete or overwrite production memory or registry files.

## Artifacts

The runner writes all artifacts under the selected work directory, including:

- synthetic fixture input JSON/JSONL
- temporary `rag_research_memory_store.jsonl`
- approved memory export preview JSON/MD
- rule candidate draft JSON/MD
- copied `approved_for_registry` draft JSON
- temporary `rag_rule_candidate_registry.jsonl`
- Trading handoff preview JSON/MD
- smoke summary JSON/MD

## Failure Checks

If the smoke fails, inspect `failed_step` in the smoke summary JSON. Common causes are:

- a synthetic answer no longer satisfies memory-store eligibility
- memory promotion did not persist to the temporary store
- approved memory preview emitted zero candidates
- draft schema validation failed
- the copied draft was not accepted by the registry updater
- the final preview omitted required DB-only, Trading Bot, or preview-only boundary language

## Not Done

- No real Trading Bot integration.
- No real automated trading signal generation.
- No real Naver Cafe access.
- No real `archive.db` write.
- No production `agent_reports/rag_research_memory_store.jsonl` mutation.
- No production `agent_reports/rag_rule_candidate_registry.jsonl` mutation.
