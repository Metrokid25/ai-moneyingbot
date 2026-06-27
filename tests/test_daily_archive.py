import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

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

    monkeypatch.setattr(daily_archive, "collect_new_articles", lambda **kwargs: rows)
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


def test_refuses_without_dry_run_or_execute(tmp_path):
    with pytest.raises(daily_archive.DailyArchiveGuard):
        daily_archive.run_daily_archive(
            dry_run=False,
            execute=False,
            state_dir=tmp_path / "state",
            reports_dir=tmp_path / "reports",
        )


def test_dry_run_and_execute_are_mutually_exclusive(tmp_path):
    with pytest.raises(daily_archive.DailyArchiveGuard):
        daily_archive.run_daily_archive(
            dry_run=True,
            execute=True,
            state_dir=tmp_path / "state",
            reports_dir=tmp_path / "reports",
        )


def test_execute_requires_list_url(tmp_path):
    with pytest.raises(daily_archive.DailyArchiveGuard):
        daily_archive.run_daily_archive(
            dry_run=False,
            execute=True,
            list_url=None,
            state_dir=tmp_path / "state",
            reports_dir=tmp_path / "reports",
        )


def test_main_refuses_real_run_without_execute():
    # No --dry-run and no --execute → blocked before any DB/file write, exit code 2.
    assert daily_archive.main([]) == 2


def test_execute_uses_injected_discovery_without_touching_db(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_discover(*, list_url, tail, estimate, on_page_error=None):
        captured.update(list_url=list_url, tail=tail, estimate=estimate)
        return [
            {"article_id": 10, "url": "https://cafe/10", "title": "a"},
            {"article_id": 11, "url": "https://cafe/11", "title": "b"},
        ]

    saved: list[int] = []
    monkeypatch.setattr(daily_archive, "init_db", lambda: None)
    monkeypatch.setattr(
        daily_archive,
        "is_duplicate",
        lambda article_id, seen_ids, *, dry_run: article_id in seen_ids,
    )
    monkeypatch.setattr(
        daily_archive,
        "save_article",
        lambda row, *, dry_run: saved.append(int(row["article_id"])),
    )

    stats, report_path = daily_archive.run_daily_archive(
        dry_run=False,
        execute=True,
        list_url="https://cafe/list",
        tail=2,
        estimate=1500,
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
        today=datetime(2026, 5, 28, tzinfo=KST),
        discover_fn=fake_discover,
    )

    # discovery received the bounded params verbatim
    assert captured == {"list_url": "https://cafe/list", "tail": 2, "estimate": 1500}
    assert stats.discovered == 2
    assert stats.saved == 2
    assert saved == [10, 11]
    # real mode writes non-dry-run state/report artifacts
    assert (tmp_path / "state" / "crawl_state.json").exists()
    assert report_path == tmp_path / "reports" / "2026-05-28.md"


def test_discover_via_index_tail_maps_rows_and_records_page_errors(monkeypatch):
    # Exercise the real _discover_via_index_tail by faking the browser + index_tail
    # primitives it calls — no network. Verifies row mapping, that a per-page fetch
    # error is surfaced via on_page_error (not silently dropped), and that the
    # delay runs on every iteration including the failing one.
    import index_tail
    import browser as browser_mod

    class FakePage:
        pass

    class FakeSession:
        def __init__(self):
            self.page = FakePage()
            self.closed = False

        def goto(self, url):
            return url, None

        def close(self):
            self.closed = True

    sleeps: list[int] = []
    monkeypatch.setattr(browser_mod, "BrowserSession", FakeSession)
    monkeypatch.setattr(browser_mod, "wait_for_login", lambda page: None)
    monkeypatch.setattr(index_tail, "find_tail", lambda session, list_url, estimate: 100)
    monkeypatch.setattr(index_tail, "_sleep", lambda: sleeps.append(1))

    def fake_fetch(session, list_url, page):
        if page == 99:
            return None, "blocked"
        return (
            [{"article_id": page * 10, "url": f"https://c/{page}", "title": f"t{page}", "posted_at": "2026"}],
            None,
        )

    monkeypatch.setattr(index_tail, "_fetch_rows", fake_fetch)

    errors: list[tuple[int, str]] = []
    rows = daily_archive._discover_via_index_tail(
        list_url="https://cafe/list",
        tail=3,
        estimate=100,
        on_page_error=lambda page, url, reason: errors.append((page, reason)),
    )

    # pages walked = [100, 99, 98]; page 99 errors, 100 and 98 yield rows
    assert [r["article_id"] for r in rows] == [1000, 980]
    assert [r["source_page"] for r in rows] == [100, 98]
    assert [r["author"] for r in rows] == ["굿머닝", "굿머닝"]
    # the blocked page is reported, not dropped
    assert errors == [(99, "blocked")]
    # delay applied once per page, including the failing one
    assert len(sleeps) == 3


def test_discover_via_index_tail_returns_empty_when_tail_not_found(monkeypatch):
    import index_tail
    import browser as browser_mod

    class FakeSession:
        page = object()

        def goto(self, url):
            return url, None

        def close(self):
            pass

    monkeypatch.setattr(browser_mod, "BrowserSession", FakeSession)
    monkeypatch.setattr(browser_mod, "wait_for_login", lambda page: None)
    monkeypatch.setattr(index_tail, "find_tail", lambda session, list_url, estimate: None)

    rows = daily_archive._discover_via_index_tail(
        list_url="https://cafe/list", tail=3, estimate=100
    )
    assert rows == []


def test_discover_via_index_tail_rejects_non_positive_tail():
    with pytest.raises(daily_archive.DailyArchiveGuard):
        daily_archive._discover_via_index_tail(
            list_url="https://cafe/list", tail=0, estimate=100
        )


def test_execute_records_page_fetch_failures_to_failed_queue(tmp_path, monkeypatch):
    # End-to-end through run_daily_archive: a discovery that reports a page error
    # must land in the failed queue and bump stats.failed.
    def fake_discover(*, list_url, tail, estimate, on_page_error=None):
        on_page_error(42, "https://cafe/list?page=42", "captcha")
        return [{"article_id": 7, "url": "https://cafe/7", "title": "ok"}]

    monkeypatch.setattr(daily_archive, "init_db", lambda: None)
    monkeypatch.setattr(
        daily_archive, "is_duplicate", lambda article_id, seen_ids, *, dry_run: False
    )
    monkeypatch.setattr(daily_archive, "save_article", lambda row, *, dry_run: None)

    stats, _ = daily_archive.run_daily_archive(
        dry_run=False,
        execute=True,
        list_url="https://cafe/list",
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
        today=datetime(2026, 5, 28, tzinfo=KST),
        discover_fn=fake_discover,
    )

    assert stats.saved == 1
    assert stats.failed == 1
    assert any("page_fetch_failed" in item["reason"] for item in stats.failed_items)


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
