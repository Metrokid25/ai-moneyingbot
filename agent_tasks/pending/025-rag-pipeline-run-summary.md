Title: Add readable RAG pipeline run summary

Context:
- scripts/run_rag_agent_pipeline.ps1 runs the RAG implementation step, review step, and optional pass-gated publish.
- Operators need a concise final summary after each pipeline run.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must not be implemented by the RAG Bot.

Goals:
- Print a human-readable summary when run_rag_agent_pipeline.ps1 completes.
- Include at least these fields in the summary:
  - pipeline result
  - review result
  - review report path
  - whether a commit was attempted and whether it succeeded
  - whether a push was attempted and whether it succeeded
  - latest commit hash
  - git status -sb output
  - remaining pending task summary
- Make the summary clear for default execution, PASS, FAIL, and NEEDS_HUMAN_REVIEW outcomes.
- Include commit/push results in the summary when -CommitOnPass or -PushOnPass is used.
- Preserve the protection rule that 001-real-daily-archive-wiring.md is Archive-owned and must not be implemented by the RAG Bot.
- Add focused tests that verify the summary contract.

Constraints:
- This seed commit creates only the task file.
- Do not implement this task while creating it.
- Do not modify code while creating this task.
- Do not modify documentation while creating this task.
- Do not touch forbidden files.
- Do not use git add ..

Forbidden:
- git add .
- .env
- archive.db
- data/
- scripts/_step3_verify_v2.py
- scripts/daily_archive.py
- scripts/index_tail.py
- scripts/batch_recollect.py
- src/browser.py
- src/parser.py
- src/collector.py
- src/indexer.py
- agent_tasks/pending/001-real-daily-archive-wiring.md implementation

Expected verification for this task creation:
- git status -sb
- git diff --check
- python scripts\agent_next_task.py --list

Completion criteria:
- agent_tasks/pending/025-rag-pipeline-run-summary.md exists.
- Only this 025 task file is staged and committed for the seed commit.
- No code or documentation implementation changes are included in the seed commit.
