Title: Improve autonomous RAG commit message readability

Context:
- The RAG autonomous loop and pipeline can publish changes automatically.
- Current automatic commit messages such as "RAG pipeline pass-gated update" are too generic.
- Operators need commit messages that show which RAG task was planned or completed.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must not be implemented by the RAG Bot.

Goals:
- Improve automatic commit message generation for RAG pipeline and autonomous loop publishing.
- When the planner creates a new task, include the generated task name in the commit message.
- Example planner message:
  - Plan next RAG task: 040-rag-focused-test-runner-coverage
- When an existing pending task is implemented and completed, include the completed task name in the commit message.
- Example completion message:
  - Complete RAG task: 040-rag-focused-test-runner-coverage
- Preserve the existing behavior where an explicit -CommitMessage supplied by the user takes priority.
- Never generate an automatic message targeting the Archive-owned 001 task.
- Add focused tests that verify commit message generation rules.

Allowed scope:
- scripts/run_rag_agent_pipeline.ps1.
- scripts/run_rag_autonomous_loop.ps1.
- scripts/agent_next_task.py if a small helper is useful.
- tests/test_rag_review_pipeline.py.
- tests/test_rag_autonomous_loop.py.
- other focused RAG tests if needed.

Forbidden:
- git add .
- .env
- archive.db
- data/
- scripts/_step3_verify_v2.py
- scripts/daily_archive.py
- scripts/index_tail.py
- scripts/batch_recollect.py
- src/browser.py
- src/parser.py
- src/collector.py
- src/indexer.py
- agent_tasks/pending/001-real-daily-archive-wiring.md implementation

Verification:
- python scripts\run_rag_focused_tests.py
- git diff --check
- python scripts\agent_next_task.py --list

Completion criteria:
- Automatic planner commits identify the planned task.
- Automatic completion commits identify the completed RAG task.
- Explicit -CommitMessage still overrides automatic messages.
- Archive-owned 001 is never used as an automatic commit message target.
- Focused tests pass.
- No forbidden files are touched.
- Move this task to agent_tasks/done/041-rag-autonomous-commit-message-readability.md when complete.
