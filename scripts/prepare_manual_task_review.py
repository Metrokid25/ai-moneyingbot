from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "agent_reports"
REQUIRED_BRANCH = "agent/rag-ingest-boundary"
ARCHIVE_OWNED_TASK = "001-real-daily-archive-wiring.md"
ARCHIVE_OWNED_TASK_ID = "001-real-daily-archive-wiring"
DEFAULT_VERIFICATION_COMMAND = "python scripts/run_rag_focused_tests.py"

FORBIDDEN_PATHS = (
    ".env",
    "archive.db",
    "data/",
    "scripts/_step3_verify_v2.py",
    "scripts/daily_archive.py",
    "scripts/index_tail.py",
    "scripts/batch_recollect.py",
    "src/browser.py",
    "src/parser.py",
    "src/collector.py",
    "src/indexer.py",
    "Trading Bot related files",
)

REVIEW_CHECKLIST = (
    "Confirm the work is RAG-only and does not touch Archive Bot or Trading Bot files.",
    "Confirm .env, archive.db, raw data/, Archive crawling/write code, and Trading Bot files are unchanged.",
    "Confirm agent_tasks/pending/001-real-daily-archive-wiring.md remains Archive-owned and was not implemented by the RAG Bot.",
    "Confirm the default verification is python scripts/run_rag_focused_tests.py, not full pytest.",
    "Confirm git diff --check passes.",
    "Confirm source changes are scoped to the manual task request.",
    "Confirm the reviewer result is PASS before any push is allowed.",
)


def normalize_space(value: Any) -> str:
    return " ".join(str(value or "").split())


def timestamp_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def slugify(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    return "-".join(part for part in slug.split("-") if part) or "manual-task"


def task_ownership_key(task_ref: str | None) -> str:
    normalized = normalize_space(task_ref).replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    if basename.endswith(".md"):
        basename = basename[: -len(".md")]
    return basename


def is_archive_owned_task(task_ref: str) -> bool:
    return task_ownership_key(task_ref) == ARCHIVE_OWNED_TASK_ID


def render_review_prompt(task_ref: str, task_title: str | None = None) -> str:
    task_ref = normalize_space(task_ref)
    task_title = normalize_space(task_title)
    title = task_title or task_ref
    archive_block = (
        f"BLOCKED FOR RAG IMPLEMENTATION: {ARCHIVE_OWNED_TASK} is an Archive-owned task. RAG Bot must not implement this task."
        if is_archive_owned_task(task_ref) or is_archive_owned_task(task_title)
        else f"Archive-owned task guard: {ARCHIVE_OWNED_TASK} must remain unimplemented by the RAG Bot."
    )

    checklist = "\n".join(f"- [ ] {item}" for item in REVIEW_CHECKLIST)
    forbidden_paths = "\n".join(f"- {path}" for path in FORBIDDEN_PATHS)

    return f"""# Manual RAG Task Review Gate

## Task

- task_ref: {task_ref}
- task_title: {title}
- branch: {REQUIRED_BRANCH}

## Push Gate

Do not push this task until an independent Codex reviewer returns PASS.
If the review result is FAIL, NEEDS_HUMAN_REVIEW, empty, or ambiguous, push is forbidden.

## Reviewer Mode

Do not implement; review only. Reviewer must not modify files, commit, or push.

## Required Operator Checks

Run these commands before asking for review:

```powershell
cd {PROJECT_ROOT}
git status -sb
git log --oneline -5
{DEFAULT_VERIFICATION_COMMAND}
git diff --check
git status -sb
```

Full pytest is not the default manual RAG task gate. Use the focused suite above unless a reviewer explicitly asks for broader validation.

## RAG Scope Guard

{archive_block}

Do not modify these paths or ownership areas:

{forbidden_paths}

Do not access Naver Cafe. Do not write archive.db. Do not mutate raw data/ originals.

## Reviewer Checklist

{checklist}

## Review Request Prompt

Please review the manual RAG task implementation for `{title}`.

Do not implement; review only. Focus on behavioral regressions, missing tests, scope violations, forbidden file changes, and whether the implementation satisfies the requested RAG task. Verify that `{DEFAULT_VERIFICATION_COMMAND}` and `git diff --check` passed. Return exactly one review result: PASS, FAIL, or NEEDS_HUMAN_REVIEW. A push is allowed only for PASS.
"""


def write_report(out_dir: Path, task_ref: str, timestamp: str, content: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"rag-manual-task-review-{timestamp}-{slugify(task_ref)}.md"
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a PASS-gated review prompt for a manual RAG task.",
    )
    parser.add_argument("task_ref", help="Manual RAG task id, filename, or short reference.")
    parser.add_argument("--task-title", default=None, help="Optional human-readable task title.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Optional report directory. When omitted, the prompt is printed to stdout.",
    )
    parser.add_argument("--timestamp", default=None, help="Report timestamp override.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    content = render_review_prompt(args.task_ref, args.task_title)
    if args.out_dir is None:
        print(content)
        return 0

    path = write_report(args.out_dir, args.task_ref, args.timestamp or timestamp_now(), content)
    print(f"Wrote manual RAG task review prompt: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
