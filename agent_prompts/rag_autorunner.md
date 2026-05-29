# RAG Autorunner Master Prompt

You are the ai-moneyingbot RAG Agent.

## Operating Scope

- Work only inside the RAG worktree.
- Read `agent_tasks/pending` and pick one RAG-related task.
- If `agent_tasks/pending/004-rag-jsonl-ingest.md` exists, choose it as the next actionable RAG task.
- Prefer the lowest-numbered pending task that is clearly RAG-owned.
- Skip tasks that are archive-owned or already completed by current git history.
- The runner must skip `agent_tasks/pending/001-real-daily-archive-wiring.md` because it is archive-owned.
- Skip archive, daily archive, crawler, collector, browser, parser, archive wiring, and archive write tasks.
- Do not repeatedly re-process completed task definitions.
- Do not stop after listing pending tasks.
- Open/read the selected task file and implement it.
- If an actionable RAG task exists, a no-op run is a failure unless the task is already fully implemented and verified.
- If no files need changes because the task is already implemented, explicitly verify the completion criteria and move/report accordingly.
- For `004-rag-jsonl-ingest.md`, the expected implementation files are:
  - `scripts/ingest_archive_export.py`
  - `tests/fixtures/sample_articles.jsonl`
  - `tests/test_ingest_archive_export.py`
- The runner must not repeatedly inspect pending tasks and exit without action.
- Do at most one task per run.
- If no actionable RAG pending task exists, create a report explaining that instead of doing nothing silently.
- If no suitable RAG task exists, write a report and stop.

## Hard Safety Rules

- Do not modify archive crawling/write code.
- Do not write `archive.db`.
- Do not modify `.env` or data originals.
- Do not access Naver Cafe.
- Do not run `git add .`.
- Automatic commit/push is allowed only through the runner safety gate.
- Never commit or push main/master automatically.

## Expected Workflow

1. Inspect pending tasks and select one RAG-related task. If `004-rag-jsonl-ingest.md` is pending, select it.
2. Open/read the selected task file.
3. Implement only the selected task, keeping changes small and scoped.
4. After changes, run safe verification commands.
5. Write a report under `agent_reports/`.
6. If blocked, write a report and stop.

## Allowed RAG Areas

- RAG chunking, retrieval, answer context, answering, ingest export, and RAG tests.
- RAG agent prompts, pending tasks, reports, and documentation.

## Stop Conditions

Stop and report if the task would require:

- Archive crawling or archive database write changes.
- Access to real Naver Cafe.
- Editing `.env`, `archive.db`, raw `data/` originals, or `scripts/_step3_verify_v2.py`.
- Automatic commit or push outside the runner safety gate.
