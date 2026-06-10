# RAG Autonomous Research Learning Loop

## Purpose

The autonomous research learning loop is a DB-only orchestrator for RAG research reports. It connects existing question retrieval and answer draft runners, then writes a compact learning summary under `agent_reports/`.

This is a first-stage runner. It does not perform AI self-evaluation, external research, Trading Bot rule updates, archive crawling, or archive writes.

## DB-only Rules

- Use only local research question JSONL, Qdrant retrieval output, and DB-grounded answer reports.
- Do not use external web search, latest news, current market data, or general economic knowledge to fill gaps.
- Do not access Naver Cafe.
- Do not write `archive.db` or raw `data/` originals.
- Do not change Archive Bot crawling/write code or Trading Bot files.
- Do not push without the existing human review/PASS gate.

## Questions File Flow

Run retrieval, answer drafting, and learning summary generation from a question report:

```powershell
python scripts\run_rag_research_learning_loop.py --questions-file agent_reports\rag-research-questions-YYYYMMDD-HHMMSS.jsonl
```

With explicit Qdrant settings:

```powershell
python scripts\run_rag_research_learning_loop.py --questions-file agent_reports\rag-research-questions-YYYYMMDD-HHMMSS.jsonl --qdrant-path .qdrant --collection goodmorning_chunks --top-k 5
```

When `--questions-file` is supplied without `--retrieval-file`, the loop runs:

1. `scripts/run_rag_research_retrieval.py`
2. `scripts/run_rag_research_answers.py`
3. learning summary report generation

## Retrieval File Flow

Skip retrieval when a retrieval report already exists:

```powershell
python scripts\run_rag_research_learning_loop.py --retrieval-file agent_reports\rag-research-retrieval-YYYYMMDD-HHMMSS.jsonl
```

The loop then runs answer drafting and the learning summary only.

## Dry Run

Preview the planned commands without generating reports:

```powershell
python scripts\run_rag_research_learning_loop.py --questions-file agent_reports\rag-research-questions-YYYYMMDD-HHMMSS.jsonl --dry-run
```

## Reports

The loop writes:

- `agent_reports/rag-learning-loop-YYYYMMDD-HHMMSS.json`
- `agent_reports/rag-learning-loop-YYYYMMDD-HHMMSS.md`

The reports include:

- `questions_file`
- `retrieval_file`
- `answer_file`
- `backend_status`
- `question_count`
- `retrieval_ok`
- `retrieval_no_results`
- `retrieval_backend_unavailable`
- `answer_ok`
- `answer_weak_evidence`
- `answer_no_evidence`
- `answer_backend_unavailable`
- weak evidence question ids
- no evidence question ids
- backend unavailable flag
- `next_learning_candidates`
- `next_actions`

## Candidate Rules

- `weak_evidence` answers become `needs_better_evidence`.
- `no_evidence` answers become `needs_retrieval_query_refinement`.
- `answer_ok` answers become `candidate_for_memory_store`.
- backend unavailable records become `fix_retrieval_backend_before_learning`.

## Not In Scope

- No external news or web enrichment.
- No current market or price interpretation.
- No automatic Trading Bot rule changes.
- No archive collection or archive DB writes.
- No commit or push without the existing review/PASS operating gate.
