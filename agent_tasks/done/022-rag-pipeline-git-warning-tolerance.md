Title: Tolerate git warning output in RAG pipeline publish gate

Context:
- scripts/run_rag_agent_pipeline.ps1 can optionally commit and push after REVIEW_RESULT=PASS.
- During a pass-gated publish run, git add can emit CRLF warnings on stderr while still exiting with code 0.
- PowerShell can surface native stderr as NativeCommandError-like output when ErrorActionPreference is Stop.
- Warning output must be logged, but must not block commit/push when the git command exit code is 0.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must not be implemented by the RAG Bot.

Goals:
- Update the publish gate so git add, git commit, and git push tolerate warning/stderr output when exit code is 0.
- Treat git command failure strictly by nonzero exit code.
- Continue logging git warning/output lines to the console.
- Keep git add . forbidden.
- Preserve forbidden path protection.
- Preserve REVIEW_RESULT gating:
  - PASS can run the optional publish gate.
  - FAIL never commits or pushes.
  - NEEDS_HUMAN_REVIEW never commits or pushes.
- Preserve default behavior: no commit or push unless explicitly requested.
- Update tests/test_rag_review_pipeline.py to cover the warning-tolerance contract.

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
- actual Naver Cafe access
- commit or push during this implementation task

Expected verification:
- python scripts\run_rag_focused_tests.py
- git diff --check
- python scripts\agent_next_task.py --list
- git status -sb

Completion criteria:
- Git warning/stderr output no longer causes publish gate failure by itself.
- Nonzero git exit codes still fail the publish gate.
- Focused tests pass.
- Task 022 is moved to agent_tasks/done.
