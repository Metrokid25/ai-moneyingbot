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
    PlannedTask(
        slug="rag-retrieval-ranking-regression",
        title="Add RAG retrieval ranking regression",
        body="""Context:
- Retrieval ranking quality can drift when scoring or result normalization changes.
- The planner needs a backlog candidate that stays fully inside fixture-backed RAG
  retrieval behavior.

Goals:
- Add a deterministic regression for ranking multiple candidate chunks.
- Prefer synthetic records or existing fixtures over external services.
- Document the expected ranking signal in the test name or assertion.

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
- Ranking behavior is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-source-deduplication-regression",
        title="Add RAG source deduplication regression",
        body="""Context:
- Answer context and source display should avoid repeated citations for the same
  underlying article when duplicate chunks are retrieved.

Goals:
- Add a focused regression for source deduplication.
- Use in-repo fixtures or synthetic chunks only.
- Keep behavior deterministic and independent of vector services.

Allowed scope:
- `src/rag_answer_context.py`
- `src/rag_answering.py`
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
- Duplicate source handling is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-answer-citation-formatting-regression",
        title="Add RAG answer citation formatting regression",
        body="""Context:
- Answer citations are part of the user-facing RAG contract.
- Small formatting drift can make answers harder to verify against sources.

Goals:
- Add or tighten a regression for citation formatting.
- Cover source labels, ordering, and missing metadata fallback where practical.
- Keep tests fixture-backed and deterministic.

Allowed scope:
- `src/rag_answering.py`
- `src/rag_answer_context.py`
- `tests/test_rag_answer_citation_contract.py`
- `tests/test_rag_answering.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_answer_citation_contract.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Citation formatting behavior is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-no-context-refusal-quality",
        title="Improve RAG no-context refusal quality",
        body="""Context:
- No-context answers should be clear that the RAG corpus has insufficient
  evidence, without inventing unsupported facts.

Goals:
- Add or tighten a focused no-context answer contract test.
- Improve refusal wording only if the test exposes a real gap.
- Keep the change independent of external services.

Allowed scope:
- `src/rag_answering.py`
- `tests/test_rag_no_context_answer_contract.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_no_context_answer_contract.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- No-context refusal behavior is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-chunk-metadata-validation",
        title="Add RAG chunk metadata validation",
        body="""Context:
- Chunk metadata flows through ingest, retrieval, and answer citation display.
- Missing or malformed metadata should be caught before it reaches answer
  assembly.

Goals:
- Add fixture-backed validation for required chunk metadata fields.
- Prefer a focused test over broad refactoring.
- Keep validation inside RAG chunking or ingest-export boundaries.

Allowed scope:
- `src/rag_chunking.py`
- `scripts/ingest_archive_export.py`
- `tests/test_rag_chunking.py`
- `tests/test_ingest_archive_export.py`
- `tests/fixtures/`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_chunking.py tests/test_ingest_archive_export.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Chunk metadata requirements are covered by focused tests.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-web-ui-smoke-regression",
        title="Add RAG web UI smoke regression",
        body="""Context:
- The local RAG web UI should continue rendering core controls and answer
  surfaces as backend behavior evolves.

Goals:
- Add or tighten a smoke test for the RAG web UI.
- Keep the test local and deterministic.
- Avoid adding external browser, crawler, or Cafe dependencies.

Allowed scope:
- `scripts/serve_rag_web.py`
- `tests/test_rag_web.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_web.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- The RAG web UI has focused smoke coverage for the selected behavior.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-pipeline-report-readability",
        title="Improve RAG pipeline report readability",
        body="""Context:
- RAG pipeline reports should make task selection, verification, and blockers easy
  to audit after autonomous runs.

Goals:
- Add or tighten coverage for RAG report content.
- Improve report wording or structure only where tests show ambiguity.
- Keep changes limited to RAG pipeline/report behavior.

Allowed scope:
- `scripts/run_rag_agent_pipeline.ps1`
- `scripts/agent_next_task.py`
- `tests/test_rag_review_pipeline.py`
- `tests/test_rag_agent_next_task.py`
- `docs/`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_review_pipeline.py tests/test_rag_agent_next_task.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- RAG report readability or auditability is covered by focused tests.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-focused-test-runner-coverage",
        title="Improve RAG focused test runner coverage",
        body="""Context:
- The focused RAG test runner is the autorunner safety gate for RAG-owned work.
- New RAG tests should be easy to include without broad, unrelated test runs.

Goals:
- Add or tighten coverage for the focused RAG test runner command list.
- Include missing RAG-only tests when appropriate.
- Keep the runner free of archive collection or write commands.

Allowed scope:
- `scripts/run_rag_focused_tests.py`
- `tests/test_rag_focused_tests.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_focused_tests.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Focused runner coverage reflects current RAG-owned tests.
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
