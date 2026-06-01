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

    total = index_tail_realtime._collect_after_snapshot(
        FakeSession(),
        "https://cafe.example/list",
        min_id=1000,
        stop_after_empty_pages=3,
    )

    assert total == 0
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

    total = index_tail_realtime._collect_after_snapshot(
        FakeSession(),
        "https://cafe.example/list",
        min_id=1000,
    )

    assert total == 0
    assert calls == [1, 2, 3, 4]
