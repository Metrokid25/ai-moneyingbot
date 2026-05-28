# Agent Workflow

This repo uses a lightweight human-approved agent workflow for archive and RAG work. It is not an auto-merge or auto-push system.

## Roles

- Archive Builder: implements archive-side work such as daily archive, collector, parser, DB write logic, retry, state, and reports.
- RAG Builder: implements RAG-side work such as chunking, embeddings, retrieval, answering, web UI, and evaluation.
- Reviewer: reviews correctness, tests, boundary violations, secret exposure, data risk, and refactor size.
- Tester: runs focused tests, full tests, dry-run commands, and reports command failures.
- Risk Guard: checks hard-stop safety conditions before commit or merge.
- Reporter: summarizes Builder/Reviewer/Tester/Risk Guard output for fast human review.

## Basic Loop

1. Pick next pending task.
2. Run Builder.
3. Run Reviewer.
4. Run Tester.
5. Run Risk Guard.
6. Run Reporter.
7. Human approves commit/push.

## Task Queue

Tasks live under:

```text
agent_tasks/
  pending/
  running/
  done/
  failed/
```

Show the next task:

```powershell
python scripts/agent_next_task.py
```

Show all queues:

```powershell
python scripts/agent_next_task.py --list
```

The helper script is read-only. It does not move task files automatically.

## Safety Rules

- No auto-merge.
- No auto-push.
- No `.env` changes.
- No data deletion.
- No destructive `archive.db` changes.
- No real Naver Cafe access without explicit execute mode and safety limits.
- No external API calls without explicit execute mode.
- Archive writes source data.
- RAG reads archive data and writes only RAG index/artifacts.
- RAG must not use archive DB write APIs.
- Archive work must not directly modify RAG vector indexes.

## Report Handling

`agent_reports/` is reserved for generated agent reports. Only `agent_reports/.gitkeep` is tracked; generated report files should remain untracked.
