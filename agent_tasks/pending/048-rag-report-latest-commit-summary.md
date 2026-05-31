Title: Add RAG report latest commit summary

Context:
- RAG run reports are easier to audit when they identify the latest commit that
  was verified or intentionally left uncommitted.
- The summary should stay read-only and avoid automatic git publishing changes.

Goals:
- Add or tighten report coverage for latest commit summary content.
- Keep behavior deterministic in tests by stubbing command output or using
  fixture text.
- Avoid changing automatic commit or push behavior.

Allowed scope:
- `scripts/run_rag_agent_pipeline.ps1`
- `scripts/review_rag_agent_run.ps1`
- `tests/test_rag_review_pipeline.py`
- `tests/test_rag_*.py`
- `docs/`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_review_pipeline.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Latest commit summary behavior is covered or documented for RAG reports.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
