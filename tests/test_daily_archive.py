import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "scripts")

import daily_archive


KST = timezone(timedelta(hours=9))


def test_crawl_state_defaults_when_missing(tmp_path):
    state = daily_archive.load_crawl_state(tmp_path / "crawl_state.json")

    assert state == {
        "last_run_at": None,
        "last_article_id": None,
        "last_article_url": None,
        "total_runs": 0,
    }


def test_crawl_state_save_and_load(tmp_path):
    path = tmp_path / "crawl_state.json"
    expected = daily_archive.default_crawl_state()
    expected.update(
        {
            "last_run_at": "2026-05-28T00:00:00+09:00",
            "last_article_id": 12345,
            "last_article_url": "https://example.test/12345",
            "total_runs": 3,
        }
    )

    daily_archive.save_crawl_state(path, expected)

    assert daily_archive.load_crawl_state(path) == expected


def test_failed_queue_save_and_load(tmp_path):
    path = tmp_path / "failed_queue.json"
    queue = daily_archive.default_failed_queue()
    daily_archive.add_failed_item(
        queue,
        article_id=12345,
        url="https://example.test/12345",
        reason="parse_failed",
        failed_at="2026-05-28T00:00:00+09:00",
    )

    daily_archive.save_failed_queue(path, queue)

    loaded = daily_archive.load_failed_queue(path)
    assert loaded["items"][0]["article_id"] == "12345"
    assert loaded["items"][0]["reason"] == "parse_failed"
    assert loaded["items"][0]["retry_count"] == 1


def test_failed_queue_increments_retry_count(tmp_path):
    queue = daily_archive.default_failed_queue()
    for _ in range(2):
        daily_archive.add_failed_item(
            queue,
            article_id=12345,
            url="https://example.test/12345",
            reason="parse_failed",
            failed_at="2026-05-28T00:00:00+09:00",
        )

    assert len(queue["items"]) == 1
    assert queue["items"][0]["retry_count"] == 2


def test_duplicate_article_is_not_saved_in_dry_run(tmp_path, monkeypatch):
    rows = [
        {"article_id": 1, "url": "mock://1", "title": "one"},
        {"article_id": 1, "url": "mock://1", "title": "one duplicate"},
        {"article_id": 2, "url": "mock://2", "title": "two"},
    ]
    saved: list[int] = []

    monkeypatch.setattr(daily_archive, "collect_new_articles", lambda *, dry_run: rows)
    monkeypatch.setattr(
        daily_archive,
        "save_article",
        lambda row, *, dry_run: saved.append(int(row["article_id"])),
    )

    stats, _ = daily_archive.run_daily_archive(
        dry_run=True,
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
        today=datetime(2026, 5, 28, tzinfo=KST),
    )

    assert stats.duplicates == 1
    assert stats.saved == 2
    assert saved == [1, 2]


def test_dry_run_creates_report_and_state_files(tmp_path):
    stats, report_path = daily_archive.run_daily_archive(
        dry_run=True,
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
        today=datetime(2026, 5, 28, 9, 0, tzinfo=KST),
    )

    assert stats.discovered == 4
    assert stats.duplicates == 1
    assert stats.saved == 2
    assert stats.failed == 1
    assert report_path == tmp_path / "reports" / "2026-05-28-dry-run.md"
    assert report_path.exists()
    assert "# Daily Archive Report - 2026-05-28" in report_path.read_text(encoding="utf-8")
    assert (tmp_path / "state" / "crawl_state.dry-run.json").exists()
    assert (tmp_path / "state" / "failed_queue.dry-run.json").exists()

    state = json.loads((tmp_path / "state" / "crawl_state.dry-run.json").read_text())
    assert state["total_runs"] == 1
    assert state["last_article_id"] == 900003


def test_write_daily_report_without_failed_items(tmp_path):
    stats = daily_archive.DailyStats(discovered=1, saved=1, dry_run=True)

    path = daily_archive.write_daily_report(
        tmp_path,
        datetime(2026, 5, 28, tzinfo=KST),
        stats,
    )

    text = path.read_text(encoding="utf-8")
    assert "## Failed Items" in text
    assert "- 없음" in text
