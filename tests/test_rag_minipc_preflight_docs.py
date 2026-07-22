from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PREFLIGHT = ROOT / "docs" / "RAG_MINIPC_PREFLIGHT.md"
DEPLOY = ROOT / "docs" / "DEPLOY_MINIPC.md"
HANDOFF = ROOT / "HANDOFF.md"
MACHINE_SYNC = ROOT / "MACHINE_SYNC.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_preflight_is_linked_from_all_handoff_entry_points():
    assert PREFLIGHT.is_file()
    for path in (DEPLOY, HANDOFF, MACHINE_SYNC):
        assert "RAG_MINIPC_PREFLIGHT.md" in read(path), path


def test_preflight_stops_on_dirty_or_unapproved_state():
    text = read(PREFLIGHT)

    assert "git fetch origin" in text
    assert "git status --short --branch" in text
    assert "git rev-list --left-right --count origin/main...HEAD" in text
    assert "dirty worktree" in text
    assert "pull`, `reset`, `checkout`, `clean`, `stash`" in text
    assert '"RAG 미니PC 배포 승인"' in text
    assert "시크릿은 존재 여부만 확인하고 값은 출력하지 않는다" in text


def test_preflight_preserves_ownership_and_unknown_wip_boundaries():
    text = read(PREFLIGHT)

    assert "archive.db`는 RAG에서 읽기 전용" in text
    assert "trading-bot 저장소와 데이터는 범위 밖" in text
    assert "scripts/_step3_verify_v2.py" in text
    assert "수정·삭제·스테이징하지 않는다" in text


def test_preflight_requires_fail_closed_asset_gate_before_deploy():
    text = read(PREFLIGHT)

    guard = text.index("scripts\\check_rag_deploy_assets.py")
    dry_run = text.index("`--dry-run --no-telegram`")
    schedule = text.index("스케줄 등록", dry_run)

    assert "status = PASS" in text
    assert "write_performed = false" in text
    assert "point_ids_match_baseline = true" in text
    assert guard < dry_run < schedule


def test_deploy_doc_treats_legacy_tag_as_historical_only():
    text = read(DEPLOY)

    assert "PM이 배포 commit/tag를 명시 승인한 뒤에만" in text
    assert "git pull --ff-only" in text
    assert "`deploy-baseline-20260705`는 과거 기준점" in text
    assert "임의로 이동하지 않는다" in text
