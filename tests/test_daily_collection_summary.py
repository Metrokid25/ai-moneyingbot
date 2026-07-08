import sys
from datetime import date
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import daily_collection_summary as dcs


def test_today_saved_count_sums_only_cycle_finished_deltas(tmp_path):
    day = date(2026, 7, 7)
    log = tmp_path / f"{day.isoformat()}.log"
    log.write_text(
        "\n".join(
            [
                "[archive_loop] title collection finished: saved_delta=0 latest_id=100",
                "[archive_loop] cycle 1 finished: returncode=0 saved_delta=2 latest_id=102",
                "[archive_loop] market schedule inactive: market-closed-23-06",
                "[archive_loop] title collection finished: saved_delta=5 latest_id=110",  # 스텝 델타(중복) — 세면 안 됨
                "[archive_loop] cycle 2 finished: returncode=0 saved_delta=3 latest_id=105",
                "[archive_loop] cycle 3 finished: returncode=1 saved_delta=0 latest_id=105",
            ]
        ),
        encoding="utf-8",
    )
    # cycle-finished 라인만: 2 + 3 + 0 = 5 (title-step의 5는 제외)
    assert dcs.today_saved_count(tmp_path, day) == 5


def test_today_saved_count_missing_log_is_zero(tmp_path):
    assert dcs.today_saved_count(tmp_path, date(2026, 7, 7)) == 0


def test_build_message_has_archive_prefix_and_counts():
    msg = dcs.build_message(date(2026, 7, 7), 26, 43546, 172728)
    lines = msg.splitlines()
    assert lines[0] == "[Archive] 일일 수집 요약"
    assert "2026-07-07 (KST)" in msg
    assert "오늘 수집: 26건" in msg
    assert "누적 총계: 43,546건" in msg
    assert "최신 글 id: 172728" in msg


def test_build_message_handles_missing_db_values():
    msg = dcs.build_message(date(2026, 7, 7), 0, None, None)
    assert "오늘 수집: 0건" in msg
    assert "누적 총계: 확인불가" in msg
    assert "최신 글 id: 확인불가" in msg
