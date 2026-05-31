import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "plan_next_rag_task.py"


def load_planner():
    spec = importlib.util.spec_from_file_location("plan_next_rag_task", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_task(root: Path, relative_path: str, title: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"Title: {title}\n", encoding="utf-8")
    return path


def test_planner_creates_one_rag_task_when_only_archive_task_is_pending(tmp_path, capsys):
    planner = load_planner()
    write_task(
        tmp_path,
        "agent_tasks/pending/001-real-daily-archive-wiring.md",
        "Archive task",
    )
    write_task(
        tmp_path,
        "agent_tasks/done/026-rag-autonomous-planner-loop.md",
        "Done planner task",
    )

    result = planner.main(["--root", str(tmp_path)])
    output = capsys.readouterr().out
    planned = sorted((tmp_path / "agent_tasks" / "pending").glob("*-rag-*.md"))

    assert result == 0
    assert len(planned) == 1
    assert planned[0].name.startswith("027-rag-")
    assert "PLANNER_CREATED_TASK=agent_tasks" in output
    text = planned[0].read_text(encoding="utf-8")
    assert "Allowed scope:" in text
    assert "Forbidden scope:" in text
    assert "Archive crawling" in text
    assert "Move this task to `agent_tasks/done/`" in text


def test_planner_skips_when_actionable_rag_task_exists(tmp_path, capsys):
    planner = load_planner()
    rag_task = write_task(
        tmp_path,
        "agent_tasks/pending/026-rag-autonomous-planner-loop.md",
        "RAG task",
    )

    result = planner.main(["--root", str(tmp_path)])
    output = capsys.readouterr().out

    assert result == 0
    assert f"PLANNER_SKIPPED_ACTIONABLE_TASK={rag_task.relative_to(tmp_path)}" in output
    assert list((tmp_path / "agent_tasks" / "pending").glob("027-*.md")) == []


def test_planner_generates_only_one_task_per_run(tmp_path):
    planner = load_planner()
    write_task(
        tmp_path,
        "agent_tasks/pending/001-real-daily-archive-wiring.md",
        "Archive task",
    )

    first = planner.plan_next_task(tmp_path)
    second = planner.plan_next_task(tmp_path)

    assert first is not None
    assert second is None
    assert len(list((tmp_path / "agent_tasks" / "pending").glob("*-rag-*.md"))) == 1


def test_planner_skips_duplicate_candidates_across_all_queues(tmp_path):
    planner = load_planner()
    write_task(
        tmp_path,
        "agent_tasks/pending/001-real-daily-archive-wiring.md",
        "Archive task",
    )
    queues = ("pending", "running", "done", "failed")
    for index, candidate in enumerate(planner.TASK_CANDIDATES[:-1], start=2):
        queue = queues[index % len(queues)]
        write_task(
            tmp_path,
            f"agent_tasks/{queue}/{index:03d}-{candidate.slug}.md",
            candidate.title,
        )

    candidate = planner.choose_candidate(tmp_path)

    assert candidate == planner.TASK_CANDIDATES[-1]


def test_planner_has_replenished_candidate_after_current_done_backlog(tmp_path):
    planner = load_planner()
    write_task(
        tmp_path,
        "agent_tasks/pending/001-real-daily-archive-wiring.md",
        "Archive task",
    )
    completed_slugs = [
        "rag-answer-context-token-budget-regression",
        "rag-retrieval-source-order-regression",
        "rag-retrieval-ranking-regression",
        "rag-source-deduplication-regression",
        "rag-answer-citation-formatting-regression",
        "rag-no-context-refusal-quality",
        "rag-chunk-metadata-validation",
        "rag-web-ui-smoke-regression",
        "rag-pipeline-report-readability",
        "rag-focused-test-runner-coverage",
    ]
    for index, slug in enumerate(completed_slugs, start=27):
        write_task(
            tmp_path,
            f"agent_tasks/done/{index:03d}-{slug}.md",
            slug.replace("-", " ").title(),
        )
    write_task(
        tmp_path,
        "agent_tasks/done/041-rag-autonomous-commit-message-readability.md",
        "Improve RAG autonomous commit message readability",
    )

    planned = planner.plan_next_task(tmp_path)

    assert planned is not None
    assert planned.name == "042-rag-retrieval-score-threshold-regression.md"
    text = planned.read_text(encoding="utf-8")
    assert "Retrieval score threshold behavior" in text
    assert "Archive crawling" in text


def test_planner_skips_equivalent_candidate_titles_across_all_queues(tmp_path):
    planner = load_planner()
    write_task(
        tmp_path,
        "agent_tasks/pending/001-real-daily-archive-wiring.md",
        "Archive task",
    )
    for index, candidate in enumerate(planner.TASK_CANDIDATES[:10], start=27):
        write_task(
            tmp_path,
            f"agent_tasks/done/{index:03d}-{candidate.slug}.md",
            candidate.title,
        )
    write_task(
        tmp_path,
        "agent_tasks/failed/099-manual-threshold-followup.md",
        "RAG retrieval score threshold regression",
    )

    candidate = planner.choose_candidate(tmp_path)

    assert candidate is not None
    assert candidate.slug == "rag-answer-source-count-limit-regression"


def test_planner_reports_no_candidate_when_all_candidates_are_duplicates(tmp_path, capsys):
    planner = load_planner()
    write_task(
        tmp_path,
        "agent_tasks/pending/001-real-daily-archive-wiring.md",
        "Archive task",
    )
    for index, candidate in enumerate(planner.TASK_CANDIDATES, start=2):
        write_task(
            tmp_path,
            f"agent_tasks/done/{index:03d}-{candidate.slug}.md",
            candidate.title,
        )

    result = planner.main(["--root", str(tmp_path)])
    output = capsys.readouterr().out

    assert result == 0
    assert "PLANNER_NO_CANDIDATE" in output
    assert list((tmp_path / "agent_tasks" / "pending").glob("*-rag-*.md")) == []
