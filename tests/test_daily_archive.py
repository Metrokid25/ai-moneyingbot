import json
import sys
import types
from datetime import datetime, timedelta, timezone

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
    assert "- none" in text
    assert "- discovered: 1" in text
    return
    assert "- 없음" in text


def test_main_without_mode_does_not_collect(monkeypatch, capsys):
    def fail_if_called(**_kwargs):
        raise AssertionError("run_daily_archive should not be called")

    monkeypatch.setattr(daily_archive, "run_daily_archive", fail_if_called)

    rc = daily_archive.main([])

    captured = capsys.readouterr()
    assert rc == 0
    assert "no collection mode selected" in captured.out
    assert "--dry-run" in captured.out
    assert "--execute" in captured.out


def test_execute_requires_explicit_limit():
    with pytest.raises(SystemExit) as exc_info:
        daily_archive.parse_args(["--execute"])

    assert exc_info.value.code == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["--execute", "--limit", "0"],
        ["--execute", "--limit", "101"],
        ["--execute", "--limit", "2", "--page-limit", "0"],
        ["--execute", "--limit", "2", "--page-limit", "11"],
    ],
)
def test_execute_rejects_out_of_range_limits(argv):
    with pytest.raises(SystemExit) as exc_info:
        daily_archive.parse_args(argv)

    assert exc_info.value.code == 2


def test_dry_run_does_not_use_execute_or_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        daily_archive,
        "collect_execute_articles",
        lambda **_kwargs: pytest.fail("execute collector should not be called"),
    )
    monkeypatch.setattr(daily_archive, "init_db", lambda: pytest.fail("init_db should not be called"))
    monkeypatch.setattr(
        daily_archive,
        "article_exists",
        lambda _article_id: pytest.fail("article_exists should not be called"),
    )
    monkeypatch.setattr(
        daily_archive,
        "upsert_article",
        lambda _article: pytest.fail("upsert_article should not be called"),
    )

    stats, _ = daily_archive.run_daily_archive(
        dry_run=True,
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
        today=datetime(2026, 5, 28, tzinfo=KST),
    )

    assert stats.dry_run is True
    assert stats.saved == 2


def test_execute_uses_mockable_collector_and_applies_limit(tmp_path, monkeypatch):
    rows = [
        {"article_id": 1, "url": "mock://1", "title": "one"},
        {"article_id": 2, "url": "mock://2", "title": "two"},
        {"article_id": 3, "url": "mock://3", "title": "three"},
    ]
    saved: list[int] = []

    monkeypatch.setattr(daily_archive, "collect_execute_articles", lambda **_kwargs: (rows, []))
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
        limit=2,
        page_limit=1,
        list_url="https://example.test/list",
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
        today=datetime(2026, 5, 28, tzinfo=KST),
    )

    assert stats.mode == "execute"
    assert stats.discovered == 2
    assert stats.saved == 2
    assert saved == [1, 2]
    assert report_path == tmp_path / "reports" / "2026-05-28.md"


def test_execute_state_is_separate_from_dry_run_state(tmp_path, monkeypatch):
    monkeypatch.setattr(daily_archive, "collect_execute_articles", lambda **_kwargs: ([], []))

    daily_archive.run_daily_archive(
        dry_run=True,
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
        today=datetime(2026, 5, 28, tzinfo=KST),
    )
    daily_archive.run_daily_archive(
        dry_run=False,
        execute=True,
        limit=2,
        page_limit=1,
        list_url=None,
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
        today=datetime(2026, 5, 28, tzinfo=KST),
    )

    assert (tmp_path / "state" / "crawl_state.dry-run.json").exists()
    assert (tmp_path / "state" / "failed_queue.dry-run.json").exists()
    assert (tmp_path / "state" / "crawl_state.json").exists()
    assert (tmp_path / "state" / "failed_queue.json").exists()


def test_execute_records_failed_item(tmp_path, monkeypatch):
    rows = [
        {
            "article_id": 10,
            "url": "mock://10",
            "title": "bad",
            "simulate_failure": "parse_failed",
        }
    ]

    monkeypatch.setattr(daily_archive, "collect_execute_articles", lambda **_kwargs: (rows, []))
    monkeypatch.setattr(daily_archive, "init_db", lambda: None)
    monkeypatch.setattr(
        daily_archive,
        "is_duplicate",
        lambda article_id, seen_ids, *, dry_run: False,
    )

    stats, _ = daily_archive.run_daily_archive(
        dry_run=False,
        execute=True,
        limit=10,
        page_limit=1,
        list_url="https://example.test/list",
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
        today=datetime(2026, 5, 28, tzinfo=KST),
    )

    queue = json.loads((tmp_path / "state" / "failed_queue.json").read_text())
    assert stats.failed == 1
    assert queue["items"][0]["article_id"] == "10"
    assert queue["items"][0]["reason"] == "parse_failed"


def test_execute_without_list_url_does_not_initialize_db(tmp_path, monkeypatch):
    called = False

    def record_init_db():
        nonlocal called
        called = True

    monkeypatch.setattr(daily_archive, "init_db", record_init_db)

    stats, _ = daily_archive.run_daily_archive(
        dry_run=False,
        execute=True,
        limit=2,
        page_limit=1,
        list_url=None,
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
        today=datetime(2026, 5, 28, tzinfo=KST),
    )

    assert stats.saved == 0
    assert not called
    assert "execute mode skipped" in stats.notes[0]


def test_execute_without_collect_body_does_not_call_body_collector(tmp_path, monkeypatch):
    rows = [{"article_id": 1, "url": "mock://1", "title": "one"}]

    monkeypatch.setattr(daily_archive, "collect_execute_articles", lambda **_kwargs: (rows, []))
    monkeypatch.setattr(daily_archive, "init_db", lambda: None)
    monkeypatch.setattr(
        daily_archive,
        "is_duplicate",
        lambda article_id, seen_ids, *, dry_run: False,
    )
    monkeypatch.setattr(daily_archive, "save_article", lambda row, *, dry_run: None)
    monkeypatch.setattr(
        daily_archive,
        "collect_article_body",
        lambda _article_id: pytest.fail("collect_article_body should not be called"),
    )

    stats, _ = daily_archive.run_daily_archive(
        dry_run=False,
        execute=True,
        limit=1,
        page_limit=1,
        list_url="https://example.test/list",
        collect_body=False,
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
        today=datetime(2026, 5, 28, tzinfo=KST),
    )

    assert stats.saved == 1


def test_collect_execute_without_list_url_does_not_open_browser():
    rows, notes = daily_archive.collect_execute_articles(
        list_url=None,
        limit=2,
        page_limit=1,
    )

    assert rows == []
    assert notes == ["execute mode skipped: --list-url was not provided"]


def test_build_page_url_replaces_page_parameter():
    url = daily_archive.build_page_url("https://example.test/list?clubid=1&page=9", 2)

    assert url == "https://example.test/list?clubid=1&page=2"


def test_collect_execute_articles_fetches_bounded_pages(monkeypatch):
    calls: list[int] = []
    closed = False

    class FakeSession:
        def close(self):
            nonlocal closed
            closed = True

    def fake_fetch_rows(_session, _list_url, page_num):
        calls.append(page_num)
        return [
            {"article_id": page_num * 10 + 1, "url": f"mock://{page_num}/1"},
            {"article_id": page_num * 10 + 2, "url": f"mock://{page_num}/2"},
        ], None

    fake_browser = types.ModuleType("browser")
    fake_browser.BrowserSession = FakeSession
    monkeypatch.setattr(daily_archive, "fetch_list_rows", fake_fetch_rows)
    monkeypatch.setitem(sys.modules, "browser", fake_browser)

    rows, notes = daily_archive.collect_execute_articles(
        list_url="https://example.test/list",
        limit=3,
        page_limit=5,
        delay_seconds=0,
    )

    assert [row["article_id"] for row in rows] == [11, 12, 21]
    assert calls == [1, 2]
    assert notes == []
    assert closed is True
