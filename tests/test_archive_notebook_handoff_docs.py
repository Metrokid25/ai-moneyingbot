import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_HANDOFF = PROJECT_ROOT / "docs" / "ARCHIVE_NOTEBOOK_HANDOFF.md"
OPERATIONS = PROJECT_ROOT / "docs" / "ARCHIVE_MINIPC_OPERATIONS.md"
HANDOFF = PROJECT_ROOT / "HANDOFF.md"


def test_notebook_handoff_is_git_tracked_startpoint():
    text = NOTEBOOK_HANDOFF.read_text(encoding="utf-8")
    handoff_text = HANDOFF.read_text(encoding="utf-8")

    assert "git pull --ff-only origin main" in text
    assert "origin/main" in text
    assert "ARCHIVE_NOTEBOOK_HANDOFF.md" in OPERATIONS.read_text(encoding="utf-8")
    assert "ARCHIVE_NOTEBOOK_HANDOFF.md" in handoff_text
    assert "별도 채팅 프롬프트는 필요 없다" in text
    assert "별도 채팅 프롬프트는 필요 없다" in handoff_text
    assert "git pull --ff-only origin main" in handoff_text


def test_notebook_handoff_files_are_actually_git_tracked():
    tracked = subprocess.run(
        [
            "git",
            "ls-files",
            "--error-unmatch",
            "HANDOFF.md",
            "docs/ARCHIVE_NOTEBOOK_HANDOFF.md",
            "docs/ARCHIVE_MINIPC_OPERATIONS.md",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert tracked.returncode == 0, tracked.stderr


def test_notebook_handoff_enforces_clean_state_before_and_after_pull():
    text = NOTEBOOK_HANDOFF.read_text(encoding="utf-8")
    first_action = text.split("## 2. 첫 행동", 1)[1].split("## 3.", 1)[0]
    dirty_check = first_action.index("git status --porcelain=v1")
    dirty_guard = first_action.index('if ($dirty.Count -ne 0)')
    pull = first_action.index("git pull --ff-only origin main")
    dirty_after = first_action.index("$dirtyAfter", pull)
    dirty_after_guard = first_action.index('if ($dirtyAfter.Count -ne 0)')
    equality_gate = first_action.index("$headCommit -ne $mainCommit", dirty_after)

    assert dirty_check < dirty_guard < pull
    assert pull < dirty_after < dirty_after_guard < equality_gate
    assert "--untracked-files=no" not in first_action
    assert "tracked, staged, or untracked changes exist; stop" in text
    assert "worktree became dirty after pull; stop" in text
    assert "HEAD does not equal origin/main; stop" in text
    assert "git add -A" in text
    assert "git clean" in text
    assert "git reset" in text
    assert "git stash" in text


def test_notebook_handoff_protects_dirty_primary_and_known_untracked_file():
    text = NOTEBOOK_HANDOFF.read_text(encoding="utf-8")

    assert r"C:\projects\naver_cafe_archive" in text
    assert r"C:\tmp\naver_cafe_archive_archivefork" in text
    assert "RAG tracked 변경 7개" in text
    assert "scripts/_step3_verify_v2.py" in text


def test_notebook_handoff_preserves_archive_contracts():
    text = NOTEBOOK_HANDOFF.read_text(encoding="utf-8")

    assert "code-0004" in text
    assert "archive.db" in text
    assert "articles 스키마는 동결" in text
    assert "scripts/notify_telegram.py" in text
    assert "scripts/run_rag_incremental_notify.py" in text
    assert "src/rag_*" in text


def test_notebook_handoff_requires_review_tests_and_handoff_update():
    text = NOTEBOOK_HANDOFF.read_text(encoding="utf-8")

    assert "PYTHONUTF8=1" in text
    assert "전체 pytest" in text
    assert "독립 다각도 리뷰" in text
    assert "main` ff-only" in text
    assert "HANDOFF.md` 최상단" in text


def test_notebook_handoff_keeps_minipc_mutations_approval_gated():
    text = NOTEBOOK_HANDOFF.read_text(encoding="utf-8")

    assert "invoke-mini-bot-codex.ps1" in text
    assert "-AllowMutation -ApprovalNote" in text
    assert "오너가 정확한 범위를" in text


def test_archive_minipc_live_deploy_snapshot_is_recorded_as_current():
    handoff_text = HANDOFF.read_text(encoding="utf-8")
    operations_text = OPERATIONS.read_text(encoding="utf-8")
    notebook_text = NOTEBOOK_HANDOFF.read_text(encoding="utf-8")
    current_entry = handoff_text.split("## 2026-08-03", 1)[1].split("---", 1)[0]

    assert "52def4d → ead7188" in current_entry
    assert "배포 전·후 60초 관찰 healthcheck" in current_entry
    assert "`HEALTHY`, rc=0" in current_entry
    assert "controller instance 1개" in current_entry
    assert "선택된 Archive PID는 7개" in current_entry
    assert "비Archive Python 종료는 0개" in current_entry
    assert "56CBA94517054572A8148F3A9EAB6218628884AC1103DF2F88488CF85719A2EA" in current_entry
    assert "2026-08-03 `ead7188`까지 반영" in operations_text
    assert "미니PC pull·재시작·60초 healthcheck를 완료" in notebook_text
