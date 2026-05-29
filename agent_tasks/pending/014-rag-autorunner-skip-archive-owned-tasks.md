Title: Make RAG autorunner skip archive-owned pending tasks

Context:
- 009 added the RAG focused test runner.
- 010 through 013 added RAG fixture and answer contract coverage.
- The only remaining pending task may be agent_tasks/pending/001-real-daily-archive-wiring.md.
- 001 is Archive-side work and must not be selected or implemented by the RAG Bot autorunner.

Goals:
- Ensure the RAG autorunner selects only RAG-owned tasks.
- Ensure Archive-owned tasks such as agent_tasks/pending/001-real-daily-archive-wiring.md are skipped even when they remain pending.
- Do not delete, modify, move to done, or move to failed any skipped Archive-owned task.
- Record a clear skip reason in the autorunner report or log.
- Use the safest task selection rule for the current repo structure, such as filename prefix, task metadata, allowlist, denylist, or a combination.
- Keep task selection deterministic when both Archive-owned and RAG-owned tasks are pending.
- If only Archive-owned tasks are pending, stop cleanly with a report explaining that no actionable RAG task exists.
- Do not implement 001.
- Do not write archive.db.
- Do not modify data/ originals.
- Do not access Naver Cafe.
- Do not touch archive crawler/parser/collector/browser code.
- Keep the behavior covered by RAG focused tests.

Allowed implementation files for next task:
- scripts/run_rag_agent_once.ps1
- agent_prompts/rag_autorunner.md
- docs/rag_autorunner.md
- tests/test_rag_autorunner_docs.py
- tests/test_rag_focused_tests.py if focused coverage is added there
- scripts/run_rag_focused_tests.py if a focused autorunner selection test is added
- tests/test_rag_autorunner_task_selection.py
- agent_reports/ only for generated reports during verification

Expected verification for next task:
- pytest tests/test_rag_autorunner_docs.py --basetemp=.tmp\pytest
- pytest tests/test_rag_autorunner_task_selection.py --basetemp=.tmp\pytest if added
- python scripts/run_rag_agent_once.ps1 -DryRun -NoCommit -NoPush if safe in the current environment
- python scripts/run_rag_focused_tests.py
- python scripts/agent_next_task.py --list
- git status -sb
- git diff --stat

Success conditions:
- When 001 is the only pending task, the RAG autorunner does not implement it.
- When a RAG-owned task is pending alongside 001, the RAG-owned task remains selectable.
- Archive-owned skipped tasks remain in pending.
- The report or log states the skip reason for Archive-owned tasks.
- python scripts/run_rag_focused_tests.py passes.

Forbidden:
- git add .
- agent_tasks/pending/001-real-daily-archive-wiring.md implementation
- moving agent_tasks/pending/001-real-daily-archive-wiring.md to done or failed
- .env modification
- archive.db write/delete/reset
- data/ original modification/deletion
- actual Naver Cafe access
- scripts/_step3_verify_v2.py
- scripts/daily_archive.py
- scripts/index_tail.py
- scripts/batch_recollect.py
- src/browser.py
- src/parser.py
- src/collector.py
- src/indexer.py

Completion criteria:
- RAG autorunner has an explicit and tested Archive-owned task skip rule.
- Skips are visible in report/log output.
- RAG-owned task selection still works.
- Focused tests pass.
- no archive-owned files are touched.
