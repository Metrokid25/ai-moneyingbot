from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
HANDOFF_DOC = PROJECT_ROOT / "docs" / "ARCHIVE_MINIPC_HANDOFF.md"
OPERATIONS_DOC = PROJECT_ROOT / "docs" / "ARCHIVE_MINIPC_OPERATIONS.md"
HANDOFF_LEDGER = PROJECT_ROOT / "HANDOFF.md"


def test_archive_minipc_handoff_is_pull_based_and_points_to_operations_runbook():
    text = HANDOFF_DOC.read_text(encoding="utf-8")

    assert "git fetch origin" in text
    assert "git merge --ff-only origin/main" in text
    assert "$head -ne $originMain" in text
    assert "--untracked-files=no" in text
    assert "tracked or staged changes exist" in text
    assert "git fetch origin failed" in text
    assert "ff-only update failed" in text
    assert "docs/ARCHIVE_MINIPC_OPERATIONS.md" in text
    assert "d8c806c" in text
    assert "ARCHIVE_MINIPC_HANDOFF.md" in OPERATIONS_DOC.read_text(encoding="utf-8")
    assert "ARCHIVE_MINIPC_HANDOFF.md" in HANDOFF_LEDGER.read_text(encoding="utf-8")


def test_archive_minipc_handoff_preserves_user_worktree_and_known_wip():
    text = HANDOFF_DOC.read_text(encoding="utf-8")

    assert "scripts/_step3_verify_v2.py" in text
    assert "git add -A" in text
    assert "git clean" in text
    assert "git reset --hard" in text
    assert "tracked 수정" in text


def test_archive_minipc_handoff_requires_pre_and_post_healthchecks():
    text = HANDOFF_DOC.read_text(encoding="utf-8")

    assert text.count("archive_healthcheck.py --observe-seconds 60") == 2
    assert "archive_healthcheck_before_rc" in text
    assert "archive_healthcheck_after_rc" in text
    assert 'if ($beforeRc -ne 0)' in text
    assert 'if ($afterRc -ne 0)' in text
    assert "HEALTHY" in text
    assert "LIVE VERIFIED" in text


def test_archive_restart_targets_only_commandline_matched_archive_pids():
    text = HANDOFF_DOC.read_text(encoding="utf-8")
    operations = OPERATIONS_DOC.read_text(encoding="utf-8")

    assert "Get-CimInstance Win32_Process" in text
    assert "run_daily_archive_loop|index_tail_realtime|batch_recollect" in text
    assert "Stop-Process -Id $proc.ProcessId" in text
    assert "Get-Process python" not in text
    assert "Get-Process python" not in operations
    assert "다른 Python은 종료하지 않는다" in text
    assert "archiveTreeIds" in text
    assert "profilePattern" in text
    assert "chrome-headless-shell.exe" in text
    assert "Disable-ScheduledTask" in text
    assert "Enable-ScheduledTask" in text
    assert "finally" in text
    assert "$watchdog.Settings.Enabled" in text
    assert 'Stop-ScheduledTask -TaskName "Archive-Watchdog" -ErrorAction Stop' in text
    assert "archive_watchdog\\.ps1" in text
    assert "Archive-Watchdog did not stop cleanly" in text


def test_archive_restart_is_one_self_contained_powershell_block():
    text = HANDOFF_DOC.read_text(encoding="utf-8")
    section = text.split("## 4. CollectLoop 안전 재시작", 1)[1].split(
        "## 5. 배포 후 라이브 검증", 1
    )[0]

    assert section.count("```powershell") == 1
    assert section.count("```") == 2
    assert section.index("$archivePythonBefore") < section.index("$residualArchivePython")
    assert section.index("$residualArchivePython") < section.index("Start-ScheduledTask")


def test_handoff_ledger_does_not_pull_before_archive_safety_gate():
    text = HANDOFF_LEDGER.read_text(encoding="utf-8")
    archive_entry = text.split("pull 기반 Archive 인수인계", 1)[1].split("---", 1)[0]

    assert "git fetch origin" in archive_entry
    assert "git pull" not in archive_entry
