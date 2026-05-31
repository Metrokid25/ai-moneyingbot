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
