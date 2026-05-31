Title: Add RAG autonomous operator mode summary

Context:
- scripts/run_rag_autonomous_loop.ps1 runs multiple RAG pipeline cycles.
- The loop currently requires an operator to read intermediate cycle logs to understand the final state.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must not be implemented by the RAG Bot.

Goals:
- Improve scripts/run_rag_autonomous_loop.ps1 with a final operator summary.
- Include total cycles, completed cycles, successful cycles, stopped reason, generated task list, completed task list, commit attempted count, commit succeeded count, push attempted count, push succeeded count, latest commit hash, final git status -sb, remaining pending summary, and failed task summary.
- Continue on PASS, PLANNER_CREATED_TASK, and NO_ACTIONABLE_TASKS.
- Stop immediately on FAIL or NEEDS_HUMAN_REVIEW and report the reason.
- Treat planner no-candidate as a normal no-action stop, not a failure.
- Preserve -CommitOnPass and -PushOnPass forwarding.
- Preserve default no-commit/no-push behavior.
- Preserve explicit -CommitMessage precedence.
- Preserve Archive-owned 001 protection and forbidden path safety by delegating to the pipeline.
- Keep git add . forbidden.
- Add focused tests for the operator summary and stop rules.

Verification:
- python scripts\run_rag_focused_tests.py
- git diff --check
- python scripts\agent_next_task.py --list
- git status -sb

Completion criteria:
- Operator summary is printed at the end of every loop run.
- Terminal and no-action states are summarized clearly.
- Focused tests pass.
- No forbidden files are touched.
- Move this task to agent_tasks/done/046-rag-autonomous-operator-mode.md when complete.
