import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "agent_next_task.py"


def load_agent_next_task():
    spec = importlib.util.spec_from_file_location("agent_next_task", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_task(root: Path, relative_path: str, title: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"Title: {title}\n", encoding="utf-8")
    return path


def test_archive_owned_task_is_not_selected_when_it_is_only_pending(tmp_path, capsys):
    agent_next_task = load_agent_next_task()
    archive_task = write_task(
        tmp_path,
        "agent_tasks/pending/001-real-daily-archive-wiring.md",
        "Archive task",
    )

    assert agent_next_task.find_next_pending(tmp_path) is None

    result = agent_next_task.print_next_task(tmp_path)
    output = capsys.readouterr().out

    assert result == 0
    assert archive_task.exists()
    assert "No actionable RAG pending agent tasks." in output
    assert "Skipped archive-owned task" in output
    assert "001-real-daily-archive-wiring.md" in output


def test_rag_task_is_selected_when_archive_task_is_also_pending(tmp_path, capsys):
    agent_next_task = load_agent_next_task()
    archive_task = write_task(
        tmp_path,
        "agent_tasks/pending/001-real-daily-archive-wiring.md",
        "Archive task",
    )
    rag_task = write_task(
        tmp_path,
        "agent_tasks/pending/014-rag-autorunner-skip-archive-owned-tasks.md",
        "RAG task",
    )

    assert agent_next_task.find_next_pending(tmp_path) == rag_task

    result = agent_next_task.print_next_task(tmp_path)
    output = capsys.readouterr().out

    assert result == 0
    assert archive_task.exists()
    assert "Next pending task: agent_tasks" in output
    assert "014-rag-autorunner-skip-archive-owned-tasks.md" in output
    assert "Skipped archive-owned task" in output
    assert "001-real-daily-archive-wiring.md" in output
