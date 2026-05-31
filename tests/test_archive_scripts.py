from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def read_repo_text(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_archive_powershell_scripts_exist_and_guard_url_value():
    start_loop = PROJECT_ROOT / "scripts" / "start_archive_loop.ps1"
    run_once = PROJECT_ROOT / "scripts" / "run_archive_once.ps1"

    assert start_loop.exists()
    assert run_once.exists()

    start_text = start_loop.read_text(encoding="utf-8")
    once_text = run_once.read_text(encoding="utf-8")

    for text in (start_text, once_text):
        assert "$ListUrl =" in text
        assert "cafe.naver.com" in text or "<멘토선생님 작성글 목록 URL>" in text
        assert "Refusing to start" in text
        assert "When the mentor teacher article list is visible" in text
        assert "No automatic login or CAPTCHA bypass is performed" in text
        assert "run_daily_archive_loop.py" in text
        assert "--interactive-login" in text

    assert "--market-schedule" in start_text
    assert "--max-runs 1" in once_text


def test_archive_shortcuts_doc_exists_with_expected_targets():
    text = read_repo_text("docs/archive_shortcuts.md")

    assert "Archive Run Once" in text
    assert "Archive Market Loop" in text
    assert "run_archive_once.ps1" in text
    assert "start_archive_loop.ps1" in text
    assert "powershell.exe -NoExit -ExecutionPolicy Bypass" in text
    assert "<멘토선생님 작성글 목록 URL>" in text


def test_archive_operation_doc_records_confirmed_success_routine():
    text = read_repo_text("docs/archive_24h_operation.md")

    assert "Confirmed Proven Operation Routine" in text
    assert "index_tail.py" in text
    assert "--collect-after-snapshot --interactive-login" in text
    assert "batch_recollect.py" in text
    assert "BODY_COLLECTED 42948" in text
    assert "latest article_id 170633" in text
    assert "scripts/run_archive_once.ps1" in text
    assert "scripts/start_archive_loop.ps1" in text
