Title: Upgrade DB-only RAG question generator quality

Context:
- The first DB-only question generator produced generic English questions and allowed mojibake topics into output.
- RAG research candidates should be natural Korean questions grounded in internal artifacts only.

Goals:
- Generate Korean-first research questions from normalized internal topics.
- Filter mojibake topics from emitted candidates and summarize filtered topics in Markdown reports.
- Use internal chunks/articles, source metadata, and eval/golden fixtures as evidence.
- Preserve reusable JSONL fields for later RAG retrieval and answering loops.

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
- `git diff --check`

Completion criteria:
- New report candidates are Korean-centered.
- Mojibake topics are not emitted as questions.
- Generic English template questions are removed.
- Internal evidence and filtered topic summaries are visible in the report.
- The focused RAG test suite passes.
