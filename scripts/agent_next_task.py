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


def task_root(project_root: Path) -> Path:
    return project_root / "agent_tasks"


def list_queue_files(project_root: Path, queue_name: str) -> list[Path]:
    queue_dir = task_root(project_root) / queue_name
    if not queue_dir.exists():
        return []
    return sorted(path for path in queue_dir.glob("*.md") if path.is_file())


def find_next_pending(project_root: Path) -> Path | None:
    tasks = list_queue_files(project_root, "pending")
    return tasks[0] if tasks else None


def print_next_task(project_root: Path) -> int:
    task = find_next_pending(project_root)
    if task is None:
        print("No pending agent tasks.")
        return 0

    print(f"Next pending task: {task.relative_to(project_root)}")
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


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show agent task queue status")
    parser.add_argument("--list", action="store_true", help="list all task queues")
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
    if args.list:
        return print_task_lists(project_root)
    return print_next_task(project_root)


if __name__ == "__main__":
    raise SystemExit(main())
