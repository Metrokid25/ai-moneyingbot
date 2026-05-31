Title: Improve RAG no-context refusal quality

Context:
- No-context answers should be clear that the RAG corpus has insufficient
  evidence, without inventing unsupported facts.

Goals:
- Add or tighten a focused no-context answer contract test.
- Improve refusal wording only if the test exposes a real gap.
- Keep the change independent of external services.

Allowed scope:
- `src/rag_answering.py`
- `tests/test_rag_no_context_answer_contract.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_no_context_answer_contract.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- No-context refusal behavior is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
