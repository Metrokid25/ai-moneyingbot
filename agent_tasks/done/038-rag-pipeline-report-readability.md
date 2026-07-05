Title: Improve RAG pipeline report readability

Context:
- RAG pipeline reports should make task selection, verification, and blockers easy
  to audit after autonomous runs.

Goals:
- Add or tighten coverage for RAG report content.
- Improve report wording or structure only where tests show ambiguity.
- Keep changes limited to RAG pipeline/report behavior.

Allowed scope:
- `scripts/run_rag_agent_pipeline.ps1`
- `scripts/agent_next_task.py`
- `tests/test_rag_review_pipeline.py`
- `tests/test_rag_agent_next_task.py`
- `docs/`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_review_pipeline.py tests/test_rag_agent_next_task.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- RAG report readability or auditability is covered by focused tests.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
