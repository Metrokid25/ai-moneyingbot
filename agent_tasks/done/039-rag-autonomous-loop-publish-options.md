Title: Forward publish options from autonomous loop

Context:
- scripts/run_rag_autonomous_loop.ps1 runs scripts/run_rag_agent_pipeline.ps1 for bounded cycles.
- A recent loop run with -CommitOnPass -PushOnPass still showed commit attempted: no and push attempted: no in pipeline summaries.
- The loop must forward publish options reliably to each pipeline cycle.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must not be implemented by the RAG Bot.

Goals:
- Fix scripts/run_rag_autonomous_loop.ps1 so -CommitOnPass is passed to each run_rag_agent_pipeline.ps1 invocation.
- Fix scripts/run_rag_autonomous_loop.ps1 so -PushOnPass is passed to each run_rag_agent_pipeline.ps1 invocation.
- Add or preserve commit message forwarding, using a safe default or per-cycle message when appropriate.
- Keep default loop execution free of automatic commit or push.
- Allow commit only when -CommitOnPass is supplied.
- Allow push only when -PushOnPass is supplied.
- Preserve immediate stop behavior for FAIL and NEEDS_HUMAN_REVIEW.
- Keep git add . forbidden.
- Preserve Archive-owned 001 protection by delegating publish safety to the pipeline.
- Add focused tests that verify publish option forwarding.

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
- git status -sb

Completion criteria:
- Move this task to agent_tasks/done/039-rag-autonomous-loop-publish-options.md.
- Loop publish options are forwarded in every cycle.
- Focused tests pass.
- No forbidden files are touched.
