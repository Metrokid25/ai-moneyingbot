"""Show the next pending agent task.

This helper is read-only: it lists or prints task markdown files and does not
move queue items or touch data/archive artifacts.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUEUE_NAMES = ("pending", "running", "done", "failed")
ARCHIVE_OWNED_TASKS = {
    "001-real-daily-archive-wiring.md",
}


def task_root(project_root: Path) -> Path:
    return project_root / "agent_tasks"


def list_queue_files(project_root: Path, queue_name: str) -> list[Path]:
    queue_dir = task_root(project_root) / queue_name
    if not queue_dir.exists():
        return []
    return sorted(path for path in queue_dir.glob("*.md") if path.is_file())


def is_rag_owned_task(path: Path) -> bool:
    return "-rag-" in path.name


def is_archive_owned_task(path: Path) -> bool:
    return path.name in ARCHIVE_OWNED_TASKS or not is_rag_owned_task(path)


def split_pending_tasks(project_root: Path) -> tuple[list[Path], list[Path]]:
    actionable: list[Path] = []
    skipped: list[Path] = []
    for task in list_queue_files(project_root, "pending"):
        if is_archive_owned_task(task):
            skipped.append(task)
        else:
            actionable.append(task)
    return actionable, skipped


def find_next_pending(project_root: Path) -> Path | None:
    tasks, _skipped = split_pending_tasks(project_root)
    return tasks[0] if tasks else None


def print_next_task(project_root: Path) -> int:
    _tasks, skipped = split_pending_tasks(project_root)
    task = find_next_pending(project_root)
    if task is None:
        print("No actionable RAG pending agent tasks.")
        for skipped_task in skipped:
            print(
                "Skipped archive-owned task: "
                f"{skipped_task.relative_to(project_root)} "
                "(not selected by RAG autorunner)"
            )
        return 0

    print(f"Next pending task: {task.relative_to(project_root)}")
    for skipped_task in skipped:
        print(
            "Skipped archive-owned task: "
            f"{skipped_task.relative_to(project_root)} "
            "(not selected by RAG autorunner)"
        )
    print()
    print(task.read_text(encoding="utf-8").rstrip())
    return 0


def print_task_lists(project_root: Path) -> int:
    for queue_name in QUEUE_NAMES:
        print(f"{queue_name}:")
        tasks = list_queue_files(project_root, queue_name)
        if not tasks:
            print("  - (none)")
            continue
        for task in tasks:
            print(f"  - {task.relative_to(project_root)}")
    return 0


def print_pending_status(project_root: Path) -> int:
    tasks, skipped = split_pending_tasks(project_root)
    if tasks:
        print("RAG_TASK")
        print(f"task={tasks[0].relative_to(project_root)}")
        print(f"selected_task={tasks[0].relative_to(project_root)}")
        print(f"actionable_count={len(tasks)}")
        print(f"skipped_count={len(skipped)}")
        for skipped_task in skipped:
            print(f"skipped={skipped_task.relative_to(project_root)}")
        return 0

    print("NO_ACTIONABLE_TASKS")
    print("selected_task=(none)")
    print("actionable_count=0")
    print(f"skipped_count={len(skipped)}")
    for skipped_task in skipped:
        print(f"skipped={skipped_task.relative_to(project_root)}")
    return 0


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show agent task queue status")
    parser.add_argument("--list", action="store_true", help="list all task queues")
    parser.add_argument(
        "--status",
        action="store_true",
        help="print machine-readable pending RAG task status",
    )
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
    if args.status:
        return print_pending_status(project_root)
    if args.list:
        return print_task_lists(project_root)
    return print_next_task(project_root)


if __name__ == "__main__":
    raise SystemExit(main())
