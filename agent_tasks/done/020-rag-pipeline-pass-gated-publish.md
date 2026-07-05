Title: Add pass-gated publish options to RAG pipeline

Context:
- RAG pending tasks 015 through 019 are complete.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must not be implemented by the RAG Bot.
- The RAG pipeline currently runs implementation and review, then waits for user approval without committing or pushing.

Goals:
- Add optional publish controls to scripts/run_rag_agent_pipeline.ps1.
- Keep the default pipeline behavior unchanged: no automatic commit or push.
- Allow commit only when -CommitOnPass is supplied and REVIEW_RESULT=PASS.
- Allow push only when -PushOnPass is supplied and the commit succeeds.
- Block all commit/push actions when REVIEW_RESULT is FAIL or NEEDS_HUMAN_REVIEW.
- Never use git add ..
- Commit only files reported by git status, including untracked files.
- Fail the publish gate if any forbidden file changed.
- Fail the publish gate if agent_tasks/pending/001-real-daily-archive-wiring.md changed.
- Support an optional commit message, with a safe default.
- Update tests/test_rag_review_pipeline.py for the new publish contract.
- Ensure scripts/run_rag_focused_tests.py includes the relevant review pipeline test.

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
- agent_tasks/pending/001-real-daily-archive-wiring.md
- actual commit or push during this implementation task

Expected verification:
- python scripts\run_rag_focused_tests.py
- git diff --check
- git status -sb
- confirm forbidden files were not modified

Completion criteria:
- Default pipeline execution still waits for user approval without commit/push.
- -CommitOnPass commits only on PASS after safety checks.
- -PushOnPass pushes only after a successful pass-gated commit.
- FAIL and NEEDS_HUMAN_REVIEW never commit or push.
- Focused tests pass.
- Task 020 is moved to agent_tasks/done.
