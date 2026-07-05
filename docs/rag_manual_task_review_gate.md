# Manual RAG Task Review Gate

## Purpose

Manual RAG tasks follow a pass-gated workflow: a human selects the task, Codex implements it, focused RAG validation runs, an independent Codex reviewer checks the result, and push happens only after `REVIEW_RESULT=PASS`.

This gate documents the manual path so direct task requests use the same safety expectations as the automated RAG runner without requiring full pytest by default.

## Standard Flow

```powershell
cd C:\projects\ai_moneyingbot_rag_agent
git status -sb
git log --oneline -5
```

Implement only the requested RAG task. After implementation, run:

```powershell
python scripts/run_rag_focused_tests.py
git diff --check
git status -sb
```

Prepare a review prompt:

```powershell
python scripts/prepare_manual_task_review.py 058-rag-manual-task-review-gate --task-title "Manual RAG task review gate"
```

To write the prompt under `agent_reports/` instead of stdout:

```powershell
python scripts/prepare_manual_task_review.py 058-rag-manual-task-review-gate --task-title "Manual RAG task review gate" --out-dir agent_reports
```

## Push Rule

Do not push until the independent reviewer returns `PASS`.

- `PASS` allows the operator to push the reviewed commit.
- `FAIL` blocks push.
- `NEEDS_HUMAN_REVIEW`, missing output, or ambiguous output blocks push.

The manual gate does not replace reviewer judgment. It provides a stable review prompt and checklist so the push decision is explicit.

## Reviewer Mode

The reviewer must review only. The reviewer must not implement additional changes, modify files, create commits, or push.

## Default Verification

The default verification command for manual RAG tasks is:

```powershell
python scripts/run_rag_focused_tests.py
```

Full pytest is not the default requirement for manual RAG tasks. Run broader tests only when the task risk or reviewer requires them.

## RAG Scope Rules

Manual RAG tasks must not modify:

- `.env`
- `archive.db`
- raw `data/` originals
- `scripts/_step3_verify_v2.py`
- `scripts/daily_archive.py`
- `scripts/index_tail.py`
- `scripts/batch_recollect.py`
- `src/browser.py`
- `src/parser.py`
- `src/collector.py`
- `src/indexer.py`
- Trading Bot related files

Manual RAG tasks must not access Naver Cafe, write the archive database, or change Archive crawling/write code.

## Archive-Owned Task Guard

`agent_tasks/pending/001-real-daily-archive-wiring.md` is Archive-owned. The RAG Bot must not implement it. If a manual request points to that task, stop the RAG implementation path and treat it as blocked for RAG ownership.

## Review Checklist

The generated review prompt asks the reviewer to confirm:

- the work is RAG-only;
- forbidden files and ownership areas are unchanged;
- `001-real-daily-archive-wiring.md` remains Archive-owned and unimplemented by the RAG Bot;
- `python scripts/run_rag_focused_tests.py` is the default validation, not full pytest;
- `git diff --check` passed;
- source changes are scoped to the requested manual task;
- push remains forbidden unless the review result is `PASS`.
