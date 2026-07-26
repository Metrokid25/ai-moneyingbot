from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_HANDOFF = PROJECT_ROOT / "docs" / "ARCHIVE_NOTEBOOK_HANDOFF.md"
OPERATIONS = PROJECT_ROOT / "docs" / "ARCHIVE_MINIPC_OPERATIONS.md"
HANDOFF = PROJECT_ROOT / "HANDOFF.md"


def test_notebook_handoff_is_git_tracked_startpoint():
    text = NOTEBOOK_HANDOFF.read_text(encoding="utf-8")

    assert "git fetch origin" in text
    assert "origin/main" in text
    assert "ARCHIVE_NOTEBOOK_HANDOFF.md" in OPERATIONS.read_text(encoding="utf-8")
    assert "ARCHIVE_NOTEBOOK_HANDOFF.md" in HANDOFF.read_text(encoding="utf-8")


def test_notebook_handoff_checks_all_dirty_state_before_fetch():
    text = NOTEBOOK_HANDOFF.read_text(encoding="utf-8")
    first_action = text.split("## 2. 첫 행동", 1)[1].split("## 3.", 1)[0]
    dirty_check = first_action.index("git status --porcelain=v1")
    fetch = first_action.index("git fetch origin")

    assert dirty_check < fetch
    assert "--untracked-files=no" not in first_action
    assert "tracked, staged, or untracked changes exist; stop" in text
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
