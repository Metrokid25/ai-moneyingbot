Title: Document RAG pipeline usage

Context:
- The RAG pipeline runner is scripts/run_rag_agent_pipeline.ps1.
- The runner can optionally publish changes after review, but default execution must remain non-publishing.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must not be implemented by the RAG Bot.

Goals:
- Add or tidy RAG pipeline usage documentation.
- Document how to run:
  - .\scripts\run_rag_agent_pipeline.ps1
- Document that the default run does not commit or push, even when review passes.
- Document -CommitOnPass:
  - commits only when REVIEW_RESULT=PASS and the publish safety gate passes.
- Document -PushOnPass:
  - pushes only after a successful pass-gated commit.
- Document -CommitMessage:
  - allows the pass-gated commit message to be supplied explicitly.
- Document REVIEW_RESULT behavior:
  - PASS allows optional pass-gated commit/push when requested.
  - FAIL blocks commit and push.
  - NEEDS_HUMAN_REVIEW blocks commit and push until a human decides next steps.
- Warn clearly that 001-real-daily-archive-wiring.md is Archive-owned and must not be implemented by the RAG Bot.

Constraints:
- Do not modify code.
- Do not touch forbidden files.
- Do not use git add ..
- Only this 021 task file should be staged for the publish test.

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

Expected verification:
- git status -sb
- git diff --check
- python scripts\agent_next_task.py --list

Completion criteria:
- The 021 task file exists in agent_tasks/pending.
- The task clearly describes RAG pipeline usage documentation requirements.
- No code files are modified.
- No forbidden files are touched.
