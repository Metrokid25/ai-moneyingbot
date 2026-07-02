import sys

sys.path.insert(0, "scripts")

import index_tail_realtime


class FakeSession:
    pass


def test_realtime_collect_stops_after_consecutive_zero_save_pages(monkeypatch):
    calls = []

    def fake_fetch_rows(_session, _list_url, page_num, **_kwargs):
        calls.append(page_num)
        return [
            {
                "article_id": 1000 + page_num,
                "url": f"https://example.test/{page_num}",
                "title": f"title {page_num}",
                "posted_at": None,
            }
        ], None

    monkeypatch.setattr(index_tail_realtime, "_fetch_rows_with_interactive_login", fake_fetch_rows)
    monkeypatch.setattr(index_tail_realtime, "article_exists", lambda _article_id: True)
    monkeypatch.setattr(index_tail_realtime, "_sleep", lambda: None)
    monkeypatch.setattr(
        index_tail_realtime,
        "upsert_article",
        lambda _article: (_ for _ in ()).throw(AssertionError("no article should be saved")),
    )

    total, stop_err = index_tail_realtime._collect_after_snapshot(
        FakeSession(),
        "https://cafe.example/list",
        min_id=1000,
        stop_after_empty_pages=3,
    )

    assert total == 0
    assert stop_err is None
    assert calls == [1, 2, 3]


def test_realtime_collect_default_keeps_original_snapshot_stop(monkeypatch):
    calls = []

    def fake_fetch_rows(_session, _list_url, page_num, **_kwargs):
        calls.append(page_num)
        article_id = 1000 + page_num if page_num < 4 else 999
        return [
            {
                "article_id": article_id,
                "url": f"https://example.test/{page_num}",
                "title": f"title {page_num}",
                "posted_at": None,
            }
        ], None

    monkeypatch.setattr(index_tail_realtime, "_fetch_rows_with_interactive_login", fake_fetch_rows)
    monkeypatch.setattr(index_tail_realtime, "article_exists", lambda _article_id: True)
    monkeypatch.setattr(index_tail_realtime, "_sleep", lambda: None)
    monkeypatch.setattr(
        index_tail_realtime,
        "upsert_article",
        lambda _article: (_ for _ in ()).throw(AssertionError("no article should be saved")),
    )

    total, stop_err = index_tail_realtime._collect_after_snapshot(
        FakeSession(),
        "https://cafe.example/list",
        min_id=1000,
    )

    assert total == 0
    assert stop_err is None
    assert calls == [1, 2, 3, 4]


def test_realtime_collect_reports_stop_error_on_block(monkeypatch):
    """차단(login_required)으로 중단되면 stop_err가 반환돼야 한다 — 성공 위장 금지."""
    monkeypatch.setattr(
        index_tail_realtime,
        "_fetch_rows_with_interactive_login",
        lambda *_args, **_kwargs: (None, "login_required: member_api code=0004 (로그인하지 않았습니다)"),
    )
    monkeypatch.setattr(index_tail_realtime, "_sleep", lambda: None)

    total, stop_err = index_tail_realtime._collect_after_snapshot(
        FakeSession(),
        "https://cafe.example/list",
        min_id=1000,
    )

    assert total == 0
    assert stop_err is not None and "login_required" in stop_err


def test_run_realtime_index_returns_nonzero_and_no_complete_on_block(monkeypatch, capsys):
    """로그인 차단 시 run_realtime_index는 'complete'를 찍지 않고 1을 반환해야
    루프의 블록신호 정지 로직이 동작한다."""
    monkeypatch.setattr(index_tail_realtime, "init_db", lambda: None)
    monkeypatch.setattr(
        index_tail_realtime, "_load_latest_snapshot", lambda: {"snapshot_max_id": 9}
    )
    monkeypatch.setattr(
        index_tail_realtime,
        "_collect_after_snapshot",
        lambda *_args, **_kwargs: (0, "login_required: member_api code=0004"),
    )

    rc = index_tail_realtime.run_realtime_index(
        "https://cafe.naver.com/ca-fe/cafes/1/members/KEY",
        FakeSession(),
    )

    out = capsys.readouterr().out
    assert rc == 1
    assert "complete" not in out
    assert "stopped: login_required" in out
