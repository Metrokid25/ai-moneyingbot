Title: Expand RAG planner candidate backlog

Context:
- scripts/plan_next_rag_task.py can create the next RAG task when no actionable RAG task is pending.
- The planner recently returned PLANNER_NO_CANDIDATE because the existing candidate pool was exhausted.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must not be implemented by the RAG Bot.

Goals:
- Expand the planner candidate pool in scripts/plan_next_rag_task.py.
- Keep all planner candidates strictly inside RAG scope.
- Never add Archive collection or write work as a planner candidate.
- Prevent creation of tasks that duplicate existing pending, running, done, or failed tasks.
- Ensure the planner can create a new RAG improvement task when pending contains only the Archive-owned 001 task.
- Add focused tests that verify planner candidate expansion and duplicate prevention.

Candidate category examples:
- Retrieval ranking regression.
- Source deduplication regression.
- Answer citation formatting regression.
- No-context refusal quality.
- Chunk metadata validation.
- Fixture coverage expansion.
- RAG web UI smoke tests.
- Pipeline report readability.
- Planner duplicate prevention.
- Focused test runner coverage.

Allowed scope:
- scripts/plan_next_rag_task.py.
- tests/test_rag_planner.py.
- tests/test_rag_*.py.
- agent_prompts/rag_mission.md if mission wording needs a small clarification.
- RAG documentation if needed for planner behavior notes.

Forbidden scope:
- Archive collection or writes.
- Naver Cafe access.
- data/ original modification.
- archive.db modification.
- .env modification.
- scripts/_step3_verify_v2.py.
- scripts/daily_archive.py.
- scripts/index_tail.py.
- scripts/batch_recollect.py.
- src/browser.py.
- src/parser.py.
- src/collector.py.
- src/indexer.py.
- agent_tasks/pending/001-real-daily-archive-wiring.md implementation.

Verification:
- python scripts\run_rag_focused_tests.py
- git diff --check
- python scripts\agent_next_task.py --list

Completion criteria:
- Planner has enough non-duplicate RAG candidates to create a next task after current done tasks.
- Pending with only 001 can produce a new RAG task.
- Duplicate candidates are skipped reliably.
- Focused tests pass.
- No forbidden files are touched.
- Move this task to agent_tasks/done/030-rag-planner-candidate-backlog-expansion.md when complete.
