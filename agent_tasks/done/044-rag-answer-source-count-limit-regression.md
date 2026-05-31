Title: Add RAG answer source count limit regression

Context:
- RAG answers should expose enough citations to audit grounding while avoiding
  noisy source lists.
- Source count limits are part of the answer display contract.

Goals:
- Add or tighten a focused regression for answer source count limiting.
- Cover ordering and truncation with deterministic synthetic context.
- Keep the test independent of external services.

Allowed scope:
- `src/rag_answer_context.py`
- `src/rag_answering.py`
- `tests/test_rag_answer_context.py`
- `tests/test_rag_answering.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_answer_context.py tests/test_rag_answering.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Answer source count limiting is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
