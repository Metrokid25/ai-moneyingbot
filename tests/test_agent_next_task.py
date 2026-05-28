import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "agent_next_task.py"


def run_agent_next_task(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        check=False,
        text=True,
        capture_output=True,
    )


def test_prints_first_pending_task(tmp_path):
    pending = tmp_path / "agent_tasks" / "pending"
    pending.mkdir(parents=True)
    (pending / "002-second.md").write_text("# Second\n", encoding="utf-8")
    (pending / "001-first.md").write_text("# First\n\nBody", encoding="utf-8")

    result = run_agent_next_task(tmp_path)

    assert result.returncode == 0
    assert "Next pending task: agent_tasks\\pending\\001-first.md" in result.stdout
    assert "# First" in result.stdout
    assert "# Second" not in result.stdout


def test_no_pending_tasks_message(tmp_path):
    result = run_agent_next_task(tmp_path)

    assert result.returncode == 0
    assert result.stdout.strip() == "No pending agent tasks."


def test_list_outputs_each_queue(tmp_path):
    for queue_name in ("pending", "running", "done", "failed"):
        queue = tmp_path / "agent_tasks" / queue_name
        queue.mkdir(parents=True)
    (tmp_path / "agent_tasks" / "running" / "010-running.md").write_text(
        "# Running\n", encoding="utf-8"
    )

    result = run_agent_next_task(tmp_path, "--list")

    assert result.returncode == 0
    for queue_name in ("pending", "running", "done", "failed"):
        assert f"{queue_name}:" in result.stdout
    assert "agent_tasks\\running\\010-running.md" in result.stdout
    assert "- (none)" in result.stdout


def test_script_does_not_touch_data_or_archive_db(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = tmp_path / "archive.db"
    data_file = data_dir / "sentinel.txt"
    data_file.write_text("keep", encoding="utf-8")
    db_path.write_text("keep-db", encoding="utf-8")

    result = run_agent_next_task(tmp_path)

    assert result.returncode == 0
    assert data_file.read_text(encoding="utf-8") == "keep"
    assert db_path.read_text(encoding="utf-8") == "keep-db"
