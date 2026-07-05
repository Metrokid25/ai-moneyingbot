Title: Add RAG pipeline publish smoke note

Context:
- The RAG pipeline supports optional pass-gated publishing.
- This task is a small documentation smoke test for the automatic publish flow.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must not be implemented by the RAG Bot.

Goals:
- Add a short smoke test note to one appropriate documentation file:
  - docs/rag_autorunner.md
  - or docs/rag_pipeline_publish_smoke.md
- Document in 3 to 5 lines that the RAG pipeline supports:
  - -CommitOnPass
  - -PushOnPass
  - -CommitMessage
- State that the default pipeline run does not commit or push.
- State that the publish gate runs only when REVIEW_RESULT=PASS and publish options request it.
- Keep the warning that 001-real-daily-archive-wiring.md is Archive-owned and must not be implemented by the RAG Bot.

Constraints:
- This task file creation is only to seed the pipeline publish smoke test.
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
- agent_tasks/pending/023-rag-pipeline-publish-smoke.md exists.
- Only this 023 task file is staged and committed for the seed commit.
- No code or documentation implementation changes are included in the seed commit.
