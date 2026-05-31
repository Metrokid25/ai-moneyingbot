Title: Add RAG answer context token budget regression

Context:
- RAG answer context assembly should stay predictable as fixtures grow.
- Existing tests cover answer context behavior but do not directly assert a
  compact budget boundary with multiple candidate chunks.

Goals:
- Add a focused regression test for answer context token budget handling.
- Use small in-repo fixtures or synthetic chunks only.
- Keep the test deterministic and independent of external services.

Allowed scope:
- `src/rag_answer_context.py`
- `tests/test_rag_answer_context.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_answer_context.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- The regression fails before the fix or documents an existing boundary.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
