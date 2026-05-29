# Add RAG focused test runner

Goal:
- Add a small, safe, RAG-only focused test runner so future RAG Bot changes can be validated without running the full pytest suite, which currently fails during collection because optional dependencies like playwright, bs4, or qdrant_client may be missing.

Scope:
- RAG-only validation.
- Do not modify Archive collection/write code.
- Do not touch `.env`, `archive.db`, data originals, or `scripts/_step3_verify_v2.py`.
- Do not access Naver Cafe.
- Do not use `git add .`.
- Do not modify `scripts/daily_archive.py`, `scripts/index_tail.py`, `scripts/batch_recollect.py`, `src/browser.py`, `src/parser.py`, `src/collector.py`, or `src/indexer.py`.

Suggested implementation:
1. Add a script such as `scripts/run_rag_focused_tests.py` or `scripts/run_rag_focused_tests.ps1`.
2. The runner should execute the currently reliable RAG-focused checks:
   - `python scripts/answer_question_phase2.py --help`
   - `pytest tests/test_rag_answering.py`
   - `pytest tests/test_rag_web.py`
   - `pytest tests/test_rag_autorunner_docs.py`
3. If there are other clearly RAG-only tests that do not require optional external dependencies, include them only after confirming they pass.
4. Document this focused test command in `docs/rag_autorunner.md` or a RAG-specific docs file.
5. Add tests for the new runner if practical, but keep the change small.
6. Ensure the runner does not call full pytest by default.
7. Ensure the runner does not require playwright, bs4, qdrant_client, Naver Cafe access, archive.db writes, or data original mutation.

Validation:
- Run the new focused RAG test command.
- Run any new or updated tests.
- `git status -sb`
- Confirm no forbidden files changed.

Forbidden:
- `git add .`
- Archive collection/write code changes
- `.env` modification
- `archive.db` write/delete/reset
- `data/` original modification/deletion
- Actual Naver Cafe access
- `scripts/_step3_verify_v2.py`
- `scripts/daily_archive.py`
- `scripts/index_tail.py`
- `scripts/batch_recollect.py`
- `src/browser.py`
- `src/parser.py`
- `src/collector.py`
- `src/indexer.py`

Completion criteria:
- A focused RAG test runner exists.
- The runner executes reliable RAG-only checks without full pytest by default.
- The focused command is documented.
- New or updated tests pass.
- No archive-owned files are touched.
