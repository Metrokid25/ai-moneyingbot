Title: Add RAG answer citation formatting regression

Context:
- Answer citations are part of the user-facing RAG contract.
- Small formatting drift can make answers harder to verify against sources.

Goals:
- Add or tighten a regression for citation formatting.
- Cover source labels, ordering, and missing metadata fallback where practical.
- Keep tests fixture-backed and deterministic.

Allowed scope:
- `src/rag_answering.py`
- `src/rag_answer_context.py`
- `tests/test_rag_answer_citation_contract.py`
- `tests/test_rag_answering.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_answer_citation_contract.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Citation formatting behavior is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
