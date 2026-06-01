Title: Add RAG question generator mojibake regression guard

Context:
- The 052 report still displayed mojibake in generated Markdown when inspected in the operator workflow.
- Question candidates must not emit broken Hangul fragments in `question`, `topic`, or report text.

Goals:
- Strengthen mojibake detection and redaction.
- Prevent broken source-derived text from appearing in JSONL or Markdown output.
- Fall back to safe DB-only seed research questions when usable internal text is too damaged.
- Add regression coverage using known mojibake fragments.

Allowed scope:
- `scripts/generate_rag_research_questions.py`
- `tests/test_rag_research_questions.py`
- `agent_reports/`
- `agent_tasks/done/`
- `docs/`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `.env`, `archive.db`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_research_questions.py --basetemp=.tmp/rag_research_questions_pytest`
- `python scripts/run_rag_focused_tests.py`
- `python scripts/generate_rag_research_questions.py`
- Inspect the newly generated report for mojibake patterns.
- `git diff --check`

Completion criteria:
- New report question/topic fields contain no mojibake.
- Filtered Topics reflects redacted mojibake input instead of reporting `none` when filtering occurred.
- Focused tests pass.
