Title: Auto-plan next RAG task when pipeline has no actionable task

Context:
- scripts/plan_next_rag_task.py and agent_prompts/rag_mission.md exist.
- scripts/run_rag_agent_pipeline.ps1 currently does not expose planner results in the pipeline flow when no actionable RAG task exists.
- agent_tasks/pending/001-real-daily-archive-wiring.md is Archive-owned work and must not be implemented by the RAG Bot.

Goals:
- Detect no actionable RAG task in the RAG pipeline.
- Call scripts/plan_next_rag_task.py when pending contains only Archive-owned work.
- Print planner result and generated task path in the pipeline summary.
- Let planner-created task changes be committed and pushed only through -CommitOnPass and -PushOnPass.
- Do not implement a generated task in the same pipeline run.
- Treat the 001-only pending state as a planner target state, not a failure.
- Preserve Archive-owned 001 protection.
- Preserve forbidden file protection.
- Keep git add . forbidden.

Tests:
- Verify the pipeline has a no-actionable-task planner call path.
- Verify generated planner task path is included in summary output.
- Verify generated tasks remain pending for the next run.
- Verify Archive-owned 001 protection remains documented in pipeline checks.
- Verify default execution does not commit or push.
- Verify planner-created changes can publish only through -CommitOnPass and -PushOnPass.
- Keep git add . absence checks.

Verification:
- python scripts\run_rag_focused_tests.py
- git diff --check
- python scripts\agent_next_task.py --list
- git status -sb

Completion criteria:
- Move this task to agent_tasks/done/028-rag-pipeline-auto-plan-on-no-action.md.
- No forbidden files are touched.
- Generated planner tasks are left for a later pipeline run.
