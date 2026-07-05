Title: Track completed tasks in autonomous operator summary

Context:
- scripts/run_rag_autonomous_loop.ps1 prints a final RAG Autonomous Operator Summary.
- Recent runs completed tasks such as 047 and 048, but the summary printed completed task list as (none).
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must not be implemented by the RAG Bot.

Goals:
- Track tasks completed during a single autonomous loop run.
- Print completed task filenames in the final operator summary.
- Print (none) only when no task was completed during that run.
- Keep output deterministic and easy to read.
- Preserve Archive-owned 001 protection and forbidden path safety by delegating to the pipeline.

Allowed scope:
- scripts/run_rag_autonomous_loop.ps1.
- scripts/run_rag_agent_pipeline.ps1 if needed.
- tests/test_rag_review_pipeline.py.
- tests/test_rag_planner.py.
- docs/ or agent_reports/ if needed.

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
- Archive crawling, parsing, collection, or writes.
- Naver Cafe access.
- agent_tasks/pending/001-real-daily-archive-wiring.md implementation.

Verification:
- pytest tests/test_rag_review_pipeline.py tests/test_rag_planner.py --basetemp=.tmp/rag_operator_summary_pytest
- python scripts\run_rag_focused_tests.py
- git diff --check
- git status -sb

Completion criteria:
- Completed task list reflects tasks moved to agent_tasks/done during the autonomous loop run.
- Completed task list prints (none) only when no task completed in the run.
- Focused tests pass.
- No forbidden files are touched.
- Move this task to agent_tasks/done/049-rag-operator-summary-completed-task-tracking.md when complete.
