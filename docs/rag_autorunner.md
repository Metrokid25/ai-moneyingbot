# RAG Autorunner

## Purpose

The RAG autorunner gives the ai-moneyingbot RAG Agent a guarded one-task execution path. It can inspect pending tasks, run Codex once, run verification, write reports, and, only after its safety gate passes, commit and push RAG-scoped changes on an `agent/rag-*` branch.

This is for RAG work only. It is not an archive crawler, archive writer, or unrestricted auto-merge system.

## Run Once

```powershell
cd C:\projects\ai_moneyingbot_rag_agent
.\.venv\Scripts\Activate.ps1
.\scripts\run_rag_agent_once.ps1
```

## Repeat

```powershell
.\scripts\run_rag_agent_loop.ps1 -Iterations 3 -SleepSeconds 300
```

Long-running mode must be explicit:

```powershell
.\scripts\run_rag_agent_loop.ps1 -Forever -SleepSeconds 600
```

## Check Without Commit

```powershell
.\scripts\run_rag_agent_once.ps1 -NoCommit
```

Commit locally but do not push:

```powershell
.\scripts\run_rag_agent_once.ps1 -NoPush
```

Dry-run mode skips Codex execution, commit, and push:

```powershell
.\scripts\run_rag_agent_once.ps1 -DryRun -NoCommit -NoPush
```

Use Codex's internal workspace sandbox only when the local Windows environment supports it:

```powershell
.\scripts\run_rag_agent_once.ps1 -UseCodexSandbox
```

## Focused RAG Tests

Use the focused RAG test runner for routine RAG Bot validation:

```powershell
python scripts/run_rag_focused_tests.py
```

This command runs only reliable RAG-focused checks and does not call full pytest by default. It avoids Archive Bot collection tests and does not require Naver Cafe access, archive DB writes, or raw `data/` mutation.

The runner uses a repo-local pytest base temp directory under `.tmp/` so focused tests do not depend on the Windows user temp directory.

The focused suite includes the fixture JSONL smoke test for the RAG ingest -> chunking -> retrieval-ready boundary.
It also includes a fixture retrieval eval that checks expected source metadata with an in-memory retrieval path.
It also includes an answer citation contract test that checks source metadata survives into answer output.

## Reports

Reports are written under `agent_reports/`. Each once-run creates a timestamped Markdown report, and Codex execution logs are written beside it when Codex is actually executed. The `.codex.log` file captures both stdout and stderr so the Markdown report can continue even when Codex exits with an error.

The report records the Codex sandbox mode as either `bypassed` or `workspace-write`.

## Windows Codex Sandbox Mode

By default, the Windows autorunner starts Codex with:

```powershell
codex exec --dangerously-bypass-approvals-and-sandbox -
```

The Codex internal sandbox is bypassed for Windows autorunner compatibility. The older `codex exec --sandbox workspace-write -` mode can fail inside automatic Windows sessions with `windows sandbox: spawn setup refresh`.

This is intentionally narrow: safety is enforced by the runner safety gate. The runner must keep branch guard, allowlist validation, forbidden path checks, `git diff --check`, no `git add .`, and main/master commit/push protection.

## What Automation Does

- Moves to the repository root.
- Lists pending agent tasks.
- Reads `agent_prompts/rag_autorunner.md`.
- Selects `agent_tasks/pending/004-rag-jsonl-ingest.md` as the next implementation task when it exists.
- Skips `agent_tasks/pending/001-real-daily-archive-wiring.md` because it is archive-owned.
- Opens and reads the selected task file before implementation.
- Treats a no-op run as a failure when an actionable RAG pending task exists, unless the task is already implemented and verified.
- Runs Codex once unless `-DryRun` is set.
- Records `git status -sb`, `git diff --stat`, `git diff --check`, task queue state, and pytest output.
- Collects changed files from Git status.
- Validates changed files against the RAG allowlist.
- Allows task completion moves from `agent_tasks/pending/` to `agent_tasks/done/`.
- Blocks forbidden paths.
- Stages only validated files one by one.
- Commits only after the safety gate passes.
- Pushes only to `origin/<current-branch>` for the current `agent/rag-*` branch.

## What Automation Never Does

- It never protects or bypasses a dirty non-RAG branch.
- It never commits or pushes `main` or `master` automatically.
- It never edits `.env`.
- It never writes, deletes, or resets `archive.db`.
- It never modifies raw `data/` originals.
- It never accesses Naver Cafe.
- It never modifies archive crawling or archive write code.
- It never allows all of `scripts/`; only named RAG-related scripts are allowlisted.
- It never repeatedly inspects pending tasks and exits without action when a RAG task is actionable.
- It never uses a bulk Git stage command.

## RAG Allowlist Notes

Task files may move through `agent_tasks/pending/`, `agent_tasks/done/`, and `agent_tasks/failed/`. RAG pipeline scripts are allowlisted by exact path, including `scripts/ingest_archive_export.py`, `scripts/build_chunks_phase2.py`, `scripts/load_qdrant_phase2.py`, `scripts/serve_rag_web.py`, `scripts/run_rag_focused_tests.py`, `scripts/run_rag_agent_once.ps1`, and `scripts/run_rag_agent_loop.ps1`.

The runner does not allow `scripts/` broadly. Archive crawler and archive write scripts remain forbidden unless explicitly handled by a human outside the RAG autorunner.

## Task Selection

When `agent_tasks/pending/004-rag-jsonl-ingest.md` exists, the autorunner should choose it as the next actionable RAG implementation task. It must read that task file and implement the requested files:

- `scripts/ingest_archive_export.py`
- `tests/fixtures/sample_articles.jsonl`
- `tests/test_ingest_archive_export.py`

The autorunner must skip `agent_tasks/pending/001-real-daily-archive-wiring.md` because that task is archive-owned. If a selected RAG task appears already complete, the autorunner must verify the completion criteria and report the result instead of silently doing nothing.

## Automatic Commit And Push Conditions

Automatic commit and push require all of these conditions:

- Current branch starts with `agent/rag-`.
- Current branch is not `main` or `master`.
- Git status shows changed files.
- Every changed file is inside the RAG allowlist.
- No forbidden path changed.
- `.env`, `archive.db`, raw `data/`, and `scripts/_step3_verify_v2.py` are untouched.
- `git diff --check` passes.
- Pytest was executed and recorded in the report.
- Staging is performed only for individually validated files.
- Push target is `origin/<current-branch>`.

If pytest collection fails because existing optional dependencies such as Playwright, BeautifulSoup, or Qdrant client are missing, the report must preserve that failure. The run may commit only when the failure is clearly unrelated to the current change and no newly added test fails.

## Windows Task Scheduler Notes

Use the repository path as the working directory:

```text
C:\projects\ai_moneyingbot_rag_agent
```

Call PowerShell with an explicit script path and parameters. Do not schedule the `-Forever` mode unless the machine is intended to keep the task running continuously. Prefer a bounded `-Iterations` value for unattended runs.

Make sure the scheduled account has:

- Access to the repository.
- A configured Git identity.
- Credentials for the intended `origin` remote.
- The same Python environment and Codex CLI available on PATH.

## Reverting A Bad Automatic Commit

First inspect the current branch and recent commits:

```powershell
git status -sb
git log --oneline -3
```

If the bad commit has not been pushed, use a normal local reset only after confirming the commit hash and branch with a human reviewer.

If the bad commit has been pushed, prefer a revert commit:

```powershell
git revert <bad-commit-sha>
git push origin HEAD
```

Do not rewrite shared history unless the repository owner explicitly approves it.
