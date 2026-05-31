Title: Add RAG autonomous cycle runner

Context:
- scripts/run_rag_agent_pipeline.ps1 can run one RAG automation pass.
- RAG automation needs a bounded loop runner that can execute multiple pipeline cycles.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must not be implemented by the RAG Bot.

Goals:
- Add scripts/run_rag_autonomous_loop.ps1.
- Accept a -Cycles N option.
- Run scripts/run_rag_agent_pipeline.ps1 once per cycle.
- Forward -CommitOnPass and -PushOnPass to run_rag_agent_pipeline.ps1 when supplied.
- Print each cycle result clearly.
- Treat PASS, PLANNER_CREATED_TASK, and NO_ACTIONABLE_TASKS as states that allow the next cycle to continue.
- Stop immediately on FAIL or NEEDS_HUMAN_REVIEW.
- Keep the default behavior free of automatic commit or push.
- Keep git add . forbidden.
- Preserve Archive-owned 001 protection.
- Add focused tests that verify the loop runner contract.

Constraints:
- Do not implement this task while creating this seed task file.
- Do not modify code while creating this seed task file.
- Do not touch forbidden files.
- Stage only this task file for the seed commit.

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

Verification:
- python scripts\run_rag_focused_tests.py
- git diff --check
- python scripts\agent_next_task.py --list

Completion criteria:
- scripts/run_rag_autonomous_loop.ps1 exists and supports bounded cycles.
- Loop runner forwards publish options only when requested.
- Loop runner stops on failure or human-review states.
- Focused tests pass.
- No forbidden files are touched.
- Move this task to agent_tasks/done/036-rag-autonomous-cycle-runner.md when complete.
