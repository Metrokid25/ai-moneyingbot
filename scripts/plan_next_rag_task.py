"""Create one future RAG task when the pending queue has no RAG work.

The planner is intentionally deterministic. It does not call external services,
does not inspect data originals, and writes only a small task markdown file
under agent_tasks/pending when the queue contains no actionable RAG task.
"""
from __future__ import annotations

import argparse
import re
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
    PlannedTask(
        slug="rag-retrieval-score-threshold-regression",
        title="Add RAG retrieval score threshold regression",
        body="""Context:
- Retrieval score thresholds should keep weak matches from being presented as
  grounded evidence.
- A fixture-level regression can document the expected boundary without
  external vector services.

Goals:
- Add or tighten a deterministic regression for retrieval score thresholding.
- Use synthetic or in-repo fixture records only.
- Keep the expected threshold behavior clear in assertions.

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
- Retrieval score threshold behavior is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-answer-source-count-limit-regression",
        title="Add RAG answer source count limit regression",
        body="""Context:
- RAG answers should expose enough citations to audit grounding while avoiding
  noisy source lists.
- Source count limits are part of the answer display contract.

Goals:
- Add or tighten a focused regression for answer source count limiting.
- Cover ordering and truncation with deterministic synthetic context.
- Keep the test independent of external services.

Allowed scope:
- `src/rag_answer_context.py`
- `src/rag_answering.py`
- `tests/test_rag_answer_context.py`
- `tests/test_rag_answering.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_answer_context.py tests/test_rag_answering.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Answer source count limiting is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-web-empty-query-handling",
        title="Add RAG web empty query handling regression",
        body="""Context:
- The local RAG web UI should handle empty or whitespace-only questions without
  invoking retrieval or answer generation.
- This behavior is user-facing and should stay deterministic.

Goals:
- Add or tighten a smoke regression for empty query handling.
- Verify the UI response is clear and local.
- Avoid external browser, crawler, or Cafe dependencies.

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
- Empty query handling is covered by a focused web UI regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-fixture-schema-validation",
        title="Add RAG fixture schema validation",
        body="""Context:
- RAG JSONL fixtures are shared by ingest, retrieval, and evaluation tests.
- A compact schema validation test can catch fixture drift before it causes
  unclear downstream failures.

Goals:
- Add validation for required RAG fixture fields and simple type expectations.
- Keep validation local to tests and existing fixtures.
- Prefer clear assertion messages over broad framework changes.

Allowed scope:
- `tests/fixtures/`
- `tests/test_rag_fixture_jsonl_smoke.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_fixture_jsonl_smoke.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Fixture schema expectations are covered by focused tests.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-report-latest-commit-summary",
        title="Add RAG report latest commit summary",
        body="""Context:
- RAG run reports are easier to audit when they identify the latest commit that
  was verified or intentionally left uncommitted.
- The summary should stay read-only and avoid automatic git publishing changes.

Goals:
- Add or tighten report coverage for latest commit summary content.
- Keep behavior deterministic in tests by stubbing command output or using
  fixture text.
- Avoid changing automatic commit or push behavior.

Allowed scope:
- `scripts/run_rag_agent_pipeline.ps1`
- `scripts/review_rag_agent_run.ps1`
- `tests/test_rag_review_pipeline.py`
- `tests/test_rag_*.py`
- `docs/`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_review_pipeline.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Latest commit summary behavior is covered or documented for RAG reports.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-planner-candidate-exhaustion-report",
        title="Add RAG planner candidate exhaustion report",
        body="""Context:
- When the planner has no candidates left, autonomous runs should leave a clear
  audit trail instead of only printing PLANNER_NO_CANDIDATE.
- The report should stay inside RAG-owned reporting paths.

Goals:
- Add or tighten coverage for planner exhaustion reporting.
- Produce a small report or clearer output when no RAG candidate can be planned.
- Keep the behavior deterministic and local.

Allowed scope:
- `scripts/plan_next_rag_task.py`
- `scripts/run_rag_agent_pipeline.ps1`
- `tests/test_rag_planner.py`
- `tests/test_rag_review_pipeline.py`
- `agent_reports/`
- `docs/`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_planner.py tests/test_rag_review_pipeline.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Candidate exhaustion behavior is covered by focused tests.
- Exhaustion reporting is clear for autonomous RAG runs.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-review-report-forbidden-path-table",
        title="Add RAG review report forbidden path table",
        body="""Context:
- RAG review reports should make forbidden path checks easy to audit.
- A compact table can clarify which protected files and directories were not
  touched during a run.

Goals:
- Add or tighten report coverage for forbidden path summaries.
- Keep the report focused on RAG autorunner safety checks.
- Avoid any archive collection, write, or data-original changes.

Allowed scope:
- `scripts/review_rag_agent_run.ps1`
- `tests/test_rag_review_pipeline.py`
- `tests/test_rag_*.py`
- `docs/`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_review_pipeline.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Forbidden path reporting is covered by a focused regression or documentation.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-answer-markdown-formatting-regression",
        title="Add RAG answer markdown formatting regression",
        body="""Context:
- RAG answers should remain readable when rendered as Markdown.
- Formatting drift can obscure citations or unsupported-answer messaging.

Goals:
- Add or tighten a regression for Markdown answer formatting.
- Cover headings, bullets, citations, or fallback text where practical.
- Keep the test deterministic and independent of external services.

Allowed scope:
- `src/rag_answering.py`
- `tests/test_rag_answering.py`
- `tests/test_rag_answer_citation_contract.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_answering.py tests/test_rag_answer_citation_contract.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Markdown formatting behavior is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-context-builder-source-ordering-regression",
        title="Add RAG context builder source ordering regression",
        body="""Context:
- Answer context source ordering affects which evidence is shown first.
- The context builder should preserve deterministic ordering when retrieval
  scores and source metadata interact.

Goals:
- Add or tighten a focused regression for context source ordering.
- Use synthetic chunks or in-repo fixtures only.
- Keep expected ordering clear in assertions.

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
- Context source ordering is covered by a focused regression.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
    PlannedTask(
        slug="rag-chunk-quality-report-cli-docs",
        title="Document RAG chunk quality report CLI",
        body="""Context:
- The chunk quality report is a RAG diagnostic tool used during fixture and
  ingestion checks.
- Its CLI behavior should be easy to discover without reading implementation
  details.

Goals:
- Add or tighten documentation for the chunk quality report CLI.
- Include expected inputs, outputs, and safe local verification commands.
- Keep documentation RAG-only and avoid archive write instructions.

Allowed scope:
- `docs/`
- `scripts/report_rag_chunk_quality.py`
- `tests/test_rag_chunk_quality_report.py`
- `tests/test_rag_*.py`

Forbidden scope:
- Archive crawling, parsing, collection, or archive writes.
- Naver Cafe access.
- `archive.db`, `.env`, raw `data/` originals, or archive-owned scripts.

Verification:
- `pytest tests/test_rag_chunk_quality_report.py --basetemp=.tmp/rag_planner_pytest`
- `python scripts/run_rag_focused_tests.py`
- `git diff --check`

Completion criteria:
- Chunk quality report CLI usage is documented or covered by focused tests.
- The focused RAG test suite passes.
- Move this task to `agent_tasks/done/` when complete.
""",
    ),
)


def task_queues_root(project_root: Path) -> Path:
    return project_root / "agent_tasks"


def normalized_key(text: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    for prefix in ("add-", "improve-", "document-"):
        if key.startswith(prefix):
            return key[len(prefix) :]
    return key


def existing_task_keys(project_root: Path) -> set[str]:
    keys: set[str] = set()
    for queue_name in QUEUE_NAMES:
        queue_dir = task_queues_root(project_root) / queue_name
        if not queue_dir.exists():
            continue
        for path in queue_dir.glob("*.md"):
            name = path.name
            stem = path.stem
            parts = stem.split("-", 1)
            slug = parts[1] if len(parts) == 2 and parts[0].isdigit() else stem
            keys.add(slug)
            keys.add(name)
            keys.add(normalized_key(slug))
            try:
                first_line = path.read_text(encoding="utf-8").splitlines()[0]
            except (OSError, UnicodeDecodeError, IndexError):
                continue
            if first_line.lower().startswith("title:"):
                keys.add(normalized_key(first_line.split(":", 1)[1]))
    return keys


def candidate_keys(candidate: PlannedTask) -> set[str]:
    return {
        candidate.slug,
        f"{candidate.slug}.md",
        normalized_key(candidate.slug),
        normalized_key(candidate.title),
    }


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
    existing = existing_task_keys(project_root)
    for candidate in TASK_CANDIDATES:
        if candidate_keys(candidate).isdisjoint(existing):
            return candidate
    return None


def write_candidate_exhaustion_report(project_root: Path) -> Path:
    report_dir = project_root / "agent_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "rag_planner_candidate_exhaustion.md"
    existing = existing_task_keys(project_root)
    lines = [
        "# RAG Planner Candidate Exhaustion",
        "",
        "The RAG planner found no actionable pending RAG task and no unused candidate.",
        "",
        f"- planner result: NO_CANDIDATE",
        f"- configured candidate count: {len(TASK_CANDIDATES)}",
        f"- existing candidate key count: {len(existing)}",
        "",
        "Next action: add a new RAG-owned candidate to scripts/plan_next_rag_task.py ",
        "or create a RAG-owned pending task manually.",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


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
            report = write_candidate_exhaustion_report(project_root)
            print(f"PLANNER_EXHAUSTION_REPORT={report.relative_to(project_root)}")
        return 0

    print(f"PLANNER_CREATED_TASK={planned.relative_to(project_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
