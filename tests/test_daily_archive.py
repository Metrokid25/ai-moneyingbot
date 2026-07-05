import json
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, "scripts")

import daily_archive


KST = timezone(timedelta(hours=9))
FAILED_QUEUE_FIELDS = {
    "article_id",
    "url",
    "reason",
    "retry_count",
    "last_failed_at",
}


def assert_failed_item_schema(item):
    assert set(item) == FAILED_QUEUE_FIELDS
    assert isinstance(item["retry_count"], int)
    assert item["retry_count"] >= 1
    assert isinstance(item["last_failed_at"], str)


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
    assert_failed_item_schema(loaded["items"][0])
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
    assert_failed_item_schema(queue["items"][0])
    assert queue["items"][0]["retry_count"] == 2


def test_failed_queue_updates_existing_target_reason_and_timestamp():
    queue = daily_archive.default_failed_queue()
    daily_archive.add_failed_item(
        queue,
        article_id=12345,
        url="https://example.test/12345",
        reason="first failure",
        failed_at="2026-05-28T00:00:00+09:00",
    )
    daily_archive.add_failed_item(
        queue,
        article_id="12345",
        url="https://example.test/12345",
        reason="second failure",
        failed_at="2026-05-28T01:00:00+09:00",
    )

    assert len(queue["items"]) == 1
    item = queue["items"][0]
    assert_failed_item_schema(item)
    assert item["reason"] == "second failure"
    assert item["retry_count"] == 2
    assert item["last_failed_at"] == "2026-05-28T01:00:00+09:00"


def test_add_failed_item_returns_the_affected_item_not_last():
    """제자리 갱신 시 반환값이 갱신된 그 항목이어야 한다(items[-1]은 무관한 마지막 항목)."""
    queue = daily_archive.default_failed_queue()
    daily_archive.add_failed_item(
        queue, article_id=1, url="u1", reason="r1", failed_at="t1"
    )
    daily_archive.add_failed_item(
        queue, article_id=2, url="u2", reason="r2", failed_at="t2"
    )
    returned = daily_archive.add_failed_item(
        queue, article_id=1, url="u1", reason="r1-again", failed_at="t3"
    )

    assert returned["article_id"] == "1"
    assert returned["reason"] == "r1-again"
    # items[-1]은 article 2 → 반환값과 달라야 오귀속이 안 난 것
    assert returned is not queue["items"][-1]
    assert queue["items"][-1]["article_id"] == "2"


def test_save_article_defaults_author_when_missing(monkeypatch):
    """member API 행에 author가 없으면 기본 저자로 채워 RAG export 드롭을 막는다."""
    captured = {}
    monkeypatch.setattr(
        daily_archive,
        "upsert_article",
        lambda article: captured.update(author=article.author),
    )

    daily_archive.save_article(
        {"article_id": 1, "url": "https://example.test/1", "title": "t"},
        dry_run=False,
    )

    assert captured["author"] == daily_archive.DEFAULT_AUTHOR


def test_failed_queue_keeps_distinct_targets_separate():
    queue = daily_archive.default_failed_queue()
    daily_archive.add_failed_item(
        queue,
        article_id=12345,
        url="https://example.test/12345",
        reason="first failure",
        failed_at="2026-05-28T00:00:00+09:00",
    )
    daily_archive.add_failed_item(
        queue,
        article_id=12345,
        url="https://example.test/other-url",
        reason="other target",
        failed_at="2026-05-28T00:10:00+09:00",
    )

    assert len(queue["items"]) == 2
    assert all(set(item) == FAILED_QUEUE_FIELDS for item in queue["items"])


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
    assert "## Safety" in text
    assert "mock data only" in text
    assert "- none" in text
    assert "- discovered: 1" in text


def test_main_without_mode_does_not_collect(monkeypatch, capsys):
    def fail_if_called(**_kwargs):
        raise AssertionError("run_daily_archive should not be called")

    monkeypatch.setattr(daily_archive, "run_daily_archive", fail_if_called)

    rc = daily_archive.main([])

    captured = capsys.readouterr()
    assert rc == 0
    assert "no collection mode selected" in captured.out
    assert "no browser, network, DB, state, or report changes were made" in captured.out
    assert "execute mode requires both --limit and --list-url" in captured.out
    assert "--login" in captured.out
    assert "--dry-run" in captured.out
    assert "--execute" in captured.out


def test_execute_requires_explicit_limit():
    with pytest.raises(SystemExit) as exc_info:
        daily_archive.parse_args(["--execute"])

    assert exc_info.value.code == 2


def test_execute_requires_list_url():
    with pytest.raises(SystemExit) as exc_info:
        daily_archive.parse_args(["--execute", "--limit", "2"])

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


def test_main_dry_run_prints_safety_notes(tmp_path, capsys):
    rc = daily_archive.main(
        [
            "--dry-run",
            "--state-dir",
            str(tmp_path / "state"),
            "--reports-dir",
            str(tmp_path / "reports"),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "safety" in captured.out
    assert "mock data only" in captured.out
    assert "notes" in captured.out


def test_main_execute_passes_headed_to_runner(monkeypatch):
    captured_kwargs = {}

    def fake_run_daily_archive(**kwargs):
        captured_kwargs.update(kwargs)
        return daily_archive.DailyStats(), "report.md"

    monkeypatch.setattr(daily_archive, "run_daily_archive", fake_run_daily_archive)

    rc = daily_archive.main(
        [
            "--execute",
            "--headed",
            "--limit",
            "1",
            "--list-url",
            "https://example.test/list",
        ]
    )

    assert rc == 0
    assert captured_kwargs["headed"] is True


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
    assert_failed_item_schema(queue["items"][0])
    assert queue["items"][0]["article_id"] == "10"
    assert queue["items"][0]["reason"] == "parse_failed"


def test_execute_list_collection_failure_records_failed_queue(tmp_path, monkeypatch):
    def fail_collect(**_kwargs):
        raise RuntimeError("list unavailable")

    monkeypatch.setattr(daily_archive, "collect_execute_articles", fail_collect)
    monkeypatch.setattr(daily_archive, "init_db", lambda: pytest.fail("init_db should not be called"))

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
    assert len(queue["items"]) == 1
    assert_failed_item_schema(queue["items"][0])
    assert queue["items"][0]["article_id"] is None
    assert queue["items"][0]["url"] == "https://example.test/list"
    assert queue["items"][0]["reason"] == "list_collection_failed: list unavailable"


def test_execute_records_malformed_row_in_failed_queue(tmp_path, monkeypatch):
    rows = [{"url": "mock://missing-id", "title": "bad row"}]

    monkeypatch.setattr(daily_archive, "collect_execute_articles", lambda **_kwargs: (rows, []))
    monkeypatch.setattr(daily_archive, "init_db", lambda: None)

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
    assert_failed_item_schema(queue["items"][0])
    assert queue["items"][0]["article_id"] is None
    assert queue["items"][0]["url"] == "mock://missing-id"
    assert "invalid article row" in queue["items"][0]["reason"]


def test_repeated_row_failure_updates_failed_queue_item(tmp_path, monkeypatch):
    rows = [{"article_id": 10, "url": "mock://10", "simulate_failure": "first"}]

    monkeypatch.setattr(daily_archive, "collect_execute_articles", lambda **_kwargs: (rows, []))
    monkeypatch.setattr(daily_archive, "init_db", lambda: None)
    monkeypatch.setattr(
        daily_archive,
        "is_duplicate",
        lambda article_id, seen_ids, *, dry_run: False,
    )

    for reason in ("first", "second"):
        rows[0]["simulate_failure"] = reason
        daily_archive.run_daily_archive(
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
    assert len(queue["items"]) == 1
    assert_failed_item_schema(queue["items"][0])
    assert queue["items"][0]["article_id"] == "10"
    assert queue["items"][0]["url"] == "mock://10"
    assert queue["items"][0]["reason"] == "second"
    assert queue["items"][0]["retry_count"] == 2


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


def test_execute_collect_body_failure_records_failed_queue(tmp_path, monkeypatch):
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
        lambda _article_id: (daily_archive.Status.INDEXED, "login_required"),
    )

    stats, _ = daily_archive.run_daily_archive(
        dry_run=False,
        execute=True,
        limit=1,
        page_limit=1,
        list_url="https://example.test/list",
        collect_body=True,
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
        today=datetime(2026, 5, 28, tzinfo=KST),
    )

    queue = json.loads((tmp_path / "state" / "failed_queue.json").read_text())
    assert stats.failed == 1
    assert stats.saved == 0
    assert_failed_item_schema(queue["items"][0])
    assert queue["items"][0]["article_id"] == "1"
    assert "body_collection_status=INDEXED" in queue["items"][0]["reason"]
    assert "block_signal=login_required" in queue["items"][0]["reason"]


def test_execute_collect_body_uses_existing_collector_path(tmp_path, monkeypatch):
    rows = [{"article_id": 1, "url": "mock://1", "title": "one"}]
    collected_body_ids = []

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
        lambda article_id: collected_body_ids.append(article_id)
        or (daily_archive.Status.BODY_COLLECTED, None),
    )

    stats, _ = daily_archive.run_daily_archive(
        dry_run=False,
        execute=True,
        limit=1,
        page_limit=1,
        list_url="https://example.test/list",
        collect_body=True,
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
        today=datetime(2026, 5, 28, tzinfo=KST),
    )

    assert stats.saved == 1
    assert stats.failed == 0
    assert collected_body_ids == [1]


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


def test_manual_login_verification_urls_include_collection_first_page():
    login_url = "https://cafe.naver.com/f-e/cafes/29082876/members/example"

    assert daily_archive.manual_login_verification_urls(login_url) == [
        login_url,
        login_url + "?page=1",
    ]


def test_collect_execute_articles_uses_index_tail_based_api(monkeypatch):
    calls = []
    closed = False
    profile_dirs = []
    headless_values = []

    class FakeSession:
        def __init__(self, **kwargs):
            profile_dirs.append(kwargs.get("user_data_dir"))
            headless_values.append(kwargs.get("headless"))

        def close(self):
            nonlocal closed
            closed = True

    def fake_collect_index_rows(session, list_url, **kwargs):
        calls.append((session, list_url, kwargs))
        return [
            {"article_id": 11, "url": "mock://1/1"},
            {"article_id": 12, "url": "mock://1/2"},
            {"article_id": 21, "url": "mock://2/1"},
        ]

    fake_browser = types.ModuleType("browser")
    fake_browser.BrowserSession = FakeSession
    fake_archive_indexing = types.ModuleType("archive_indexing")
    fake_archive_indexing.collect_index_rows = fake_collect_index_rows
    monkeypatch.setattr(
        daily_archive,
        "fetch_list_rows",
        lambda *_args: pytest.fail("deprecated fetch_list_rows should not be used by execute"),
    )
    monkeypatch.setitem(sys.modules, "browser", fake_browser)
    monkeypatch.setitem(sys.modules, "archive_indexing", fake_archive_indexing)

    rows, notes = daily_archive.collect_execute_articles(
        list_url="https://example.test/list",
        limit=3,
        page_limit=5,
        delay_seconds=0,
        browser_profile_dir="profile-test",
    )

    assert [row["article_id"] for row in rows] == [11, 12, 21]
    assert calls[0][1] == "https://example.test/list"
    assert calls[0][2] == {
        "limit": 3,
        "page_limit": 5,
        "delay_seconds": 0,
    }
    assert notes == ["execute: using proven index_tail-style list indexing path"]
    assert closed is True
    assert profile_dirs == ["profile-test"]
    assert headless_values == [None]


def test_collect_execute_articles_headed_passes_headless_false(monkeypatch):
    session_kwargs = []

    class FakeSession:
        def __init__(self, **kwargs):
            session_kwargs.append(kwargs)

        def close(self):
            pass

    fake_browser = types.ModuleType("browser")
    fake_browser.BrowserSession = FakeSession
    fake_archive_indexing = types.ModuleType("archive_indexing")
    fake_archive_indexing.collect_index_rows = lambda *_args, **_kwargs: []
    monkeypatch.setitem(sys.modules, "browser", fake_browser)
    monkeypatch.setitem(sys.modules, "archive_indexing", fake_archive_indexing)
    monkeypatch.setattr(
        daily_archive,
        "fetch_list_rows",
        lambda *_args: pytest.fail("deprecated fetch_list_rows should not be used by execute"),
    )

    rows, notes = daily_archive.collect_execute_articles(
        list_url="https://example.test/list",
        limit=1,
        page_limit=1,
        headed=True,
    )

    assert rows == []
    assert notes == ["execute: using proven index_tail-style list indexing path"]
    assert session_kwargs[0]["headless"] is False


def test_fetch_list_rows_waits_until_article_marker_appears(monkeypatch):
    monkeypatch.setattr(daily_archive, "LIST_PAGE_READY_DELAY_SECONDS", 0)
    page_url = "https://cafe.naver.com/f-e/cafes/1/members/example?page=1"
    htmls = [
        '<html><script>window.e="NotLoggedInError"</script></html>',
        """
        <div class="article-board">
          <table><tbody><tr>
            <td class="td_article"><a href="/ArticleRead.nhn?articleid=123">ready</a></td>
            <td class="td_date">2026.05.31</td>
          </tr></tbody></table>
        </div>
        """,
    ]

    class FakePage:
        url = page_url

        def title(self):
            return ""

    class FakeSession:
        page = FakePage()

        def __init__(self):
            self.html_calls = 0

        def goto(self, url):
            assert url == page_url
            return url, "login_required"

        def get_frame_html(self):
            html = htmls[self.html_calls]
            self.html_calls += 1
            return html, None

    session = FakeSession()

    rows, err = daily_archive.fetch_list_rows(
        session,
        "https://cafe.naver.com/f-e/cafes/1/members/example",
        1,
    )

    assert err is None
    assert [row["article_id"] for row in rows] == [123]
    assert session.html_calls == 2


def test_fetch_list_rows_rechecks_ambiguous_empty_title_page(monkeypatch):
    monkeypatch.setattr(daily_archive, "LIST_PAGE_READY_DELAY_SECONDS", 0)
    page_url = "https://cafe.naver.com/f-e/cafes/1/members/example?page=1"
    htmls = [
        "<html></html>",
        "<html><body>loading</body></html>",
        """
        <div class="article-board">
          <table><tbody><tr>
            <td class="td_article"><a href="/ArticleRead.nhn?articleid=456">ready</a></td>
          </tr></tbody></table>
        </div>
        """,
    ]

    class FakePage:
        url = page_url

        def title(self):
            return ""

    class FakeSession:
        page = FakePage()

        def __init__(self):
            self.html_calls = 0

        def goto(self, url):
            return url, None

        def get_frame_html(self):
            html = htmls[self.html_calls]
            self.html_calls += 1
            return html, None

    session = FakeSession()

    rows, err = daily_archive.fetch_list_rows(
        session,
        "https://cafe.naver.com/f-e/cafes/1/members/example",
        1,
    )

    assert err is None
    assert [row["article_id"] for row in rows] == [456]
    assert session.html_calls == 3


def test_fetch_list_rows_reports_safe_login_diagnostics(monkeypatch, capsys):
    monkeypatch.setattr(daily_archive, "LIST_PAGE_READY_DELAY_SECONDS", 0)
    page_url = "https://cafe.naver.com/f-e/cafes/1/members/example?page=1"

    class FakePage:
        url = page_url

        def title(self):
            return "Naver Login"

    class FakeSession:
        page = FakePage()

        def __init__(self):
            self.html_calls = 0

        def goto(self, url):
            return url, None

        def get_frame_html(self):
            self.html_calls += 1
            return '<form><input id="id"><input type="password"></form>', None

    session = FakeSession()

    rows, err = daily_archive.fetch_list_rows(
        session,
        "https://cafe.naver.com/f-e/cafes/1/members/example",
        1,
    )

    captured = capsys.readouterr()
    assert rows is None
    assert err == "login_required"
    assert session.html_calls == 1
    assert "article_markers_found=false" in captured.out
    assert "login_markers_found=true" in captured.out
    assert "password_input_found=true" in captured.out
    assert "current_url_is_login=false" in captured.out
    assert "cookie" not in captured.out.lower()
    assert "session" not in captured.out.lower()
    assert "<form" not in captured.out


def test_login_mode_opens_profile_without_collecting_or_writing(tmp_path, monkeypatch, capsys):
    calls = []
    closed = False
    login_url = "https://cafe.naver.com/f-e/cafes/29082876/members/example"
    page_url = login_url + "?page=1"
    goto_results = [
        ("https://nid.naver.com/login", "login_required"),
        (login_url, None),
        (page_url, None),
    ]

    class FakeSession:
        def __init__(self, **kwargs):
            calls.append(("session", kwargs.get("user_data_dir"), kwargs.get("headless")))
            self.page = object()

        def goto(self, url):
            calls.append(("goto", url))
            return goto_results.pop(0)

        def close(self):
            nonlocal closed
            closed = True

    fake_browser = types.ModuleType("browser")
    fake_browser.BrowserSession = FakeSession
    monkeypatch.setitem(sys.modules, "browser", fake_browser)
    monkeypatch.setattr(daily_archive, "wait_for_manual_confirmation", lambda: calls.append(("wait_for_enter", None)))
    monkeypatch.setattr(
        daily_archive,
        "run_daily_archive",
        lambda **_kwargs: pytest.fail("run_daily_archive should not be called"),
    )
    monkeypatch.setattr(daily_archive, "save_article", lambda *_args, **_kwargs: pytest.fail("save_article should not be called"))
    monkeypatch.setattr(daily_archive, "write_daily_report", lambda *_args, **_kwargs: pytest.fail("write_daily_report should not be called"))
    monkeypatch.setattr(daily_archive, "save_crawl_state", lambda *_args, **_kwargs: pytest.fail("save_crawl_state should not be called"))

    rc = daily_archive.main(
        [
            "--login",
            "--login-url",
            login_url,
            "--browser-profile-dir",
            str(tmp_path / "profile"),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "manual login mode" in captured.out
    assert "browser mode: headed" in captured.out
    assert "article-list page appears accessible" in captured.out
    assert "this command does not collect articles" in captured.out
    assert "do not put this command in Windows Task Scheduler" in captured.out
    assert ("session", tmp_path / "profile", False) in calls
    assert calls.count(("goto", login_url)) == 2
    assert calls.count(("goto", page_url)) == 1
    assert any(call[0] == "wait_for_enter" for call in calls)
    assert closed is True
    assert not (tmp_path / "state").exists()
    assert not (tmp_path / "reports").exists()


def test_login_mode_without_login_url_keeps_safe_default(tmp_path, monkeypatch, capsys):
    calls = []

    class FakeSession:
        def __init__(self, **kwargs):
            calls.append(("session", kwargs.get("user_data_dir")))
            self.page = object()

        def goto(self, url):
            calls.append(("goto", url))
            return url, None

        def close(self):
            calls.append(("close", None))

    fake_browser = types.ModuleType("browser")
    fake_browser.BrowserSession = FakeSession
    monkeypatch.setitem(sys.modules, "browser", fake_browser)
    monkeypatch.setattr(daily_archive, "wait_for_manual_confirmation", lambda: calls.append(("wait_for_enter", None)))

    rc = daily_archive.main(["--login", "--browser-profile-dir", str(tmp_path / "profile")])

    captured = capsys.readouterr()
    assert rc == 0
    assert ("goto", "https://nid.naver.com/nidlogin.login") in calls
    assert "카페 접근 확인을 위해 --login-url 사용 권장" in captured.out
    assert "recommended: use --login-url to confirm Cafe access" in captured.out


def test_login_mode_retries_and_fails_when_login_url_stays_blocked(tmp_path, monkeypatch, capsys):
    calls = []
    login_url = "https://cafe.naver.com/f-e/cafes/29082876/members/example"

    class FakeSession:
        def __init__(self, **kwargs):
            calls.append(("session", kwargs.get("user_data_dir"), kwargs.get("headless")))
            self.page = object()

        def goto(self, url):
            calls.append(("goto", url))
            return url, "login_required"

        def close(self):
            calls.append(("close", None))

    fake_browser = types.ModuleType("browser")
    fake_browser.BrowserSession = FakeSession
    monkeypatch.setitem(sys.modules, "browser", fake_browser)
    monkeypatch.setattr(daily_archive, "wait_for_manual_confirmation", lambda: calls.append(("wait_for_enter", None)))
    monkeypatch.setattr(
        daily_archive,
        "run_daily_archive",
        lambda **_kwargs: pytest.fail("run_daily_archive should not be called"),
    )
    monkeypatch.setattr(daily_archive, "save_article", lambda *_args, **_kwargs: pytest.fail("save_article should not be called"))
    monkeypatch.setattr(daily_archive, "write_daily_report", lambda *_args, **_kwargs: pytest.fail("write_daily_report should not be called"))
    monkeypatch.setattr(daily_archive, "save_crawl_state", lambda *_args, **_kwargs: pytest.fail("save_crawl_state should not be called"))

    rc = daily_archive.main(
        [
            "--login",
            "--login-url",
            login_url,
            "--login-check-retries",
            "2",
            "--browser-profile-dir",
            str(tmp_path / "profile"),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "still login_required" in captured.out
    assert "manual login verification failed" in captured.out
    assert ("session", tmp_path / "profile", False) in calls
    assert calls.count(("goto", login_url)) == 3
    assert len([call for call in calls if call[0] == "wait_for_enter"]) == 2


def test_daily_archive_help_lists_login_and_profile_options(capsys):
    with pytest.raises(SystemExit) as exc_info:
        daily_archive.parse_args(["--help"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "--login" in captured.out
    assert "--login-url" in captured.out
    assert "--login-check-retries" in captured.out
    assert "--headed" in captured.out
    assert "--browser-profile-dir" in captured.out
