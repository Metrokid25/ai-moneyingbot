Title: Add RAG source deduplication regression

Context:
- Answer context and source display should avoid repeated citations for the same
  underlying article when duplicate chunks are retrieved.

Goals:
- Add a focused regression for source deduplication.
- Use in-repo fixtures or synthetic chunks only.
- Keep behavior deterministic and independent of vector services.

Allowed scope:
- `src/rag_answer_context.py`
- `src/rag_answering.py`
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
- Duplicate source handling is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
