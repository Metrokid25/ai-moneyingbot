Title: Add no-actionable-task exit for RAG pipeline

Context:
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must not be implemented by the RAG Bot.
- When 001 is the only pending task, the RAG pipeline has no actionable RAG task.
- The pipeline should distinguish "nothing for RAG to do" from failure or human-review states.

Goals:
- Improve RAG pipeline exit behavior when no actionable RAG task exists.
- Treat the state where pending contains only the Archive-owned 001 task as non-failure.
- Return or report a clear result such as NO_ACTION or NO_ACTIONABLE_TASKS when there is no actionable RAG task.
- Ensure this no-action state never commits or pushes.
- Avoid collapsing no-action into only NEEDS_HUMAN_REVIEW; keep "nothing to do" distinct.
- Review the necessary scope across:
  - scripts/agent_next_task.py
  - scripts/run_rag_agent_once.ps1
  - scripts/review_rag_agent_run.ps1
  - scripts/run_rag_agent_pipeline.ps1
- Add focused tests that verify the no-actionable-task behavior.
- Preserve the protection rule that 001-real-daily-archive-wiring.md is Archive-owned and must not be implemented by the RAG Bot.

Constraints:
- This seed commit creates only the task file.
- Do not implement this task while creating it.
- Do not modify code while creating this task.
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
- agent_tasks/pending/024-rag-pipeline-no-actionable-task-exit.md exists.
- Only this 024 task file is staged and committed for the seed commit.
- No code or documentation implementation changes are included in the seed commit.
