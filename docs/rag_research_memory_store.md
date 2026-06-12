# RAG Research Memory Store

## Purpose

The research memory store keeps reusable notes from the DB-only RAG research learning loop. The 060 loop identifies answer drafts that are good enough to remember; this store appends those accepted facts into `agent_reports/rag_research_memory_store.jsonl` with stable memory IDs.

## DB-only Rules

- Use only internal DB retrieval output, answer JSONL, learning loop summaries, agent reports, fixtures, and docs.
- Do not use external web search, latest news, current market data, or general economic knowledge to fill gaps.
- Do not access Naver Cafe.
- Do not perform archive writes, write `archive.db`, or mutate raw `data/` originals.
- Do not change Archive Bot crawling/write code or Trading Bot files.

## Flow

Run the memory update from an existing learning loop summary:

```powershell
python scripts\update_rag_research_memory_store.py --learning-loop-file agent_reports\rag-learning-loop-YYYYMMDD-HHMMSS.json
```

The updater reads `answer_file` from the learning loop JSON. You can override it explicitly:

```powershell
python scripts\update_rag_research_memory_store.py --learning-loop-file agent_reports\rag-learning-loop-YYYYMMDD-HHMMSS.json --answer-file agent_reports\rag-research-answers-YYYYMMDD-HHMMSS.jsonl
```

The updater stores answer rows when either condition is true:

- the answer JSONL row has `answer_status` of `ok` or `answer_ok`
- the learning loop summary marks the question as `candidate_for_memory_store`

Each memory record includes the question, answer, evidence strength, source references, used sources, input report paths, tags, and a `pending_human_review` promotion status.

## Dry Run

Preview counts and reports without writing the memory store:

```powershell
python scripts\update_rag_research_memory_store.py --learning-loop-file agent_reports\rag-learning-loop-YYYYMMDD-HHMMSS.json --dry-run
```

`--dry-run` still writes the summary update report, but it does not create or modify `rag_research_memory_store.jsonl`.

## Learning Loop Integration

The learning loop does not touch memory by default. Opt in explicitly:

```powershell
python scripts\run_rag_research_learning_loop.py --retrieval-file agent_reports\rag-research-retrieval-YYYYMMDD-HHMMSS.jsonl --update-memory-store
```

Use a custom store path when needed:

```powershell
python scripts\run_rag_research_learning_loop.py --retrieval-file agent_reports\rag-research-retrieval-YYYYMMDD-HHMMSS.jsonl --update-memory-store --memory-store-file agent_reports\rag_research_memory_store.jsonl
```

When the learning loop itself runs with `--dry-run`, the memory store is also skipped.

## Idempotency

The updater reads the existing JSONL store before appending. It regenerates `memory_id` from the question, answer, answer status, source references, and used source payload. If the same `memory_id` already exists, the row is skipped as a duplicate.

Running the same input twice should produce `added_count: 0` on the second run and increase `skipped_duplicate_count` instead of appending another row.

## Reports

Each run writes:

- `agent_reports/rag-research-memory-update-YYYYMMDD-HHMMSS.json`
- `agent_reports/rag-research-memory-update-YYYYMMDD-HHMMSS.md`

The reports include the learning loop file, answer file, memory store path, candidate count, added count, duplicate skips, non-OK skips, stored memory IDs, dry-run flag, and the DB-only safety notice.

## Not In Scope

- No automatic Trading Bot rule updates.
- No external news or current market enrichment.
- No automatic promotion of `weak_evidence`.
- No push without human approval.
