Title: Replenish RAG planner candidate backlog

Context:
- scripts/plan_next_rag_task.py can create the next RAG task when no actionable RAG task is pending.
- The planner recently returned PLANNER_NO_CANDIDATE because the candidate pool was exhausted again.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must continue to be skipped by the RAG Bot.

Goals:
- Expand the candidate pool in scripts/plan_next_rag_task.py again.
- Prevent duplicate task creation when equivalent tasks already exist in done, pending, running, or failed queues.
- Ensure that when all current candidates are exhausted, the planner can still propose small documentation, test, regression, or report improvements.
- Never create planner candidates for Archive collection or Archive writes.
- Keep 001-real-daily-archive-wiring.md Archive-owned and skipped.
- Add focused tests that verify the replenished candidate pool and duplicate prevention.

Candidate examples:
- Retrieval score threshold regression.
- Answer source count limit regression.
- Web UI empty query handling.
- Fixture schema validation.
- Report latest commit summary.
- Planner candidate exhaustion report.
- Review report forbidden path table.
- RAG answer markdown formatting regression.
- Context builder source ordering regression.
- Chunk quality report CLI docs.

Allowed scope:
- scripts/plan_next_rag_task.py.
- tests/test_rag_planner.py.
- tests/test_rag_*.py.
- RAG docs or reports if needed.

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
- Archive collection or writes.
- Naver Cafe access.
- agent_tasks/pending/001-real-daily-archive-wiring.md implementation.

Verification:
- python scripts\run_rag_focused_tests.py
- git diff --check
- python scripts\agent_next_task.py --list

Completion criteria:
- Planner can create at least one non-duplicate RAG improvement task after the current done backlog.
- Candidate exhaustion behavior is covered by focused tests.
- Duplicate prevention is covered by focused tests.
- No forbidden files are touched.
- Move this task to agent_tasks/done/042-rag-planner-candidate-replenishment.md when complete.
