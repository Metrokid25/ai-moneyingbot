Title: Add RAG planner candidate exhaustion report

Context:
- When the planner has no candidates left, autonomous runs should leave a clear
  audit trail instead of only printing PLANNER_NO_CANDIDATE.
- The report should stay inside RAG-owned reporting paths.

Goals:
- Add or tighten coverage for planner exhaustion reporting.
- Produce a small report or clearer output when no RAG candidate can be planned.
- Keep the behavior deterministic and local.

Allowed scope:
- `scripts/plan_next_rag_task.py`
- `scripts/run_rag_agent_pipeline.ps1`
- `tests/test_rag_planner.py`
- `tests/test_rag_review_pipeline.py`
- `agent_reports/`
- `docs/`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_planner.py tests/test_rag_review_pipeline.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Candidate exhaustion behavior is covered by focused tests.
- Exhaustion reporting is clear for autonomous RAG runs.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
