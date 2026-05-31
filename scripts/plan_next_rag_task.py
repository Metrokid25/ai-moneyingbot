"""Create one future RAG task when the pending queue has no RAG work.

The planner is intentionally deterministic. It does not call external services,
does not inspect data originals, and writes only a small task markdown file
under agent_tasks/pending when the queue contains no actionable RAG task.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, NamedTuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import agent_next_task


PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUEUE_NAMES = ("pending", "running", "done", "failed")


class PlannedTask(NamedTuple):
    slug: str
    title: str
    body: str


TASK_CANDIDATES: tuple[PlannedTask, ...] = (
    PlannedTask(
        slug="rag-answer-context-token-budget-regression",
        title="Add RAG answer context token budget regression",
        body="""Context:
- RAG answer context assembly should stay predictable as fixtures grow.
- Existing tests cover answer context behavior but do not directly assert a
  compact budget boundary with multiple candidate chunks.

Goals:
- Add a focused regression test for answer context token budget handling.
- Use small in-repo fixtures or synthetic chunks only.
- Keep the test deterministic and independent of external services.

Allowed scope:
- `src/rag_answer_context.py`
- `tests/test_rag_answer_context.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_answer_context.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- The regression fails before the fix or documents an existing boundary.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-retrieval-source-order-regression",
        title="Add RAG retrieval source ordering regression",
        body="""Context:
- Retrieval result ordering affects answer grounding and displayed sources.
- A small fixture-level regression can guard against accidental ordering drift.

Goals:
- Add a deterministic retrieval ordering test using synthetic or fixture data.
- Keep the test independent of external vector services.

Allowed scope:
- `src/rag_retrieval.py`
- `tests/test_rag_retrieval*.py`
- `tests/fixtures/`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_retrieval.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Retrieval ordering behavior is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
)


def task_queues_root(project_root: Path) -> Path:
    return project_root / "agent_tasks"


def existing_task_slugs(project_root: Path) -> set[str]:
    slugs: set[str] = set()
    for queue_name in QUEUE_NAMES:
        queue_dir = task_queues_root(project_root) / queue_name
        if not queue_dir.exists():
            continue
        for path in queue_dir.glob("*.md"):
            name = path.name
            stem = path.stem
            parts = stem.split("-", 1)
            slugs.add(parts[1] if len(parts) == 2 and parts[0].isdigit() else stem)
            slugs.add(name)
    return slugs


def next_task_number(project_root: Path) -> int:
    highest = 0
    for queue_name in QUEUE_NAMES:
        queue_dir = task_queues_root(project_root) / queue_name
        if not queue_dir.exists():
            continue
        for path in queue_dir.glob("*.md"):
            prefix = path.stem.split("-", 1)[0]
            if prefix.isdigit():
                highest = max(highest, int(prefix))
    return highest + 1


def choose_candidate(project_root: Path) -> PlannedTask | None:
    existing = existing_task_slugs(project_root)
    for candidate in TASK_CANDIDATES:
        if candidate.slug not in existing and f"{candidate.slug}.md" not in existing:
            return candidate
    return None


def render_task(number: int, task: PlannedTask) -> str:
    return f"Title: {task.title}\n\n{task.body.strip()}\n"


def plan_next_task(project_root: Path) -> Path | None:
    actionable, _skipped = agent_next_task.split_pending_tasks(project_root)
    if actionable:
        return None

    candidate = choose_candidate(project_root)
    if candidate is None:
        return None

    pending_dir = task_queues_root(project_root) / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    task_number = next_task_number(project_root)
    task_path = pending_dir / f"{task_number:03d}-{candidate.slug}.md"
    task_path.write_text(render_task(task_number, candidate), encoding="utf-8")
    return task_path


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan the next small RAG task")
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT_ROOT,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = args.root.resolve()
    planned = plan_next_task(project_root)
    if planned is None:
        actionable = agent_next_task.find_next_pending(project_root)
        if actionable is not None:
            print(f"PLANNER_SKIPPED_ACTIONABLE_TASK={actionable.relative_to(project_root)}")
        else:
            print("PLANNER_NO_CANDIDATE")
        return 0

    print(f"PLANNER_CREATED_TASK={planned.relative_to(project_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
