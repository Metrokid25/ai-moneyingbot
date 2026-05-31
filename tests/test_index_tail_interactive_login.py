import sys

sys.path.insert(0, "scripts")

import index_tail


class FakeSession:
    def __init__(self):
        self.page = object()
        self.goto_calls = []

    def goto(self, url):
        self.goto_calls.append(url)
        return url, None

    def close(self):
        pass


def test_fetch_rows_interactive_login_waits_and_retries_same_session(monkeypatch):
    session = FakeSession()
    calls = []
    prompts = []

    def fake_fetch_rows(fetch_session, list_url, page_num):
        calls.append((fetch_session, list_url, page_num))
        if len(calls) == 1:
            return None, "login_required"
        return [{"article_id": 10, "url": "u", "title": "t", "posted_at": None}], None

    monkeypatch.setattr(index_tail, "_fetch_rows", fake_fetch_rows)

    rows, err = index_tail._fetch_rows_with_interactive_login(
        session,
        "https://cafe.example/list",
        1,
        interactive_login=True,
        input_func=lambda prompt: prompts.append(prompt),
    )

    assert err is None
    assert rows[0]["article_id"] == 10
    assert len(calls) == 2
    assert calls[0][0] is session
    assert calls[1][0] is session
    assert len(prompts) == 1


def test_fetch_rows_interactive_login_fails_after_retry_limit(monkeypatch):
    session = FakeSession()
    prompts = []
    calls = []

    def fake_fetch_rows(fetch_session, _list_url, _page_num):
        calls.append(fetch_session)
        return None, "login_required"

    monkeypatch.setattr(index_tail, "_fetch_rows", fake_fetch_rows)

    rows, err = index_tail._fetch_rows_with_interactive_login(
        session,
        "https://cafe.example/list",
        1,
        interactive_login=True,
        input_func=lambda prompt: prompts.append(prompt),
        max_retries=2,
    )

    assert rows is None
    assert err == "login_required"
    assert calls == [session, session, session]
    assert len(prompts) == 2


def test_fetch_rows_noninteractive_does_not_wait(monkeypatch):
    prompts = []

    monkeypatch.setattr(
        index_tail,
        "_fetch_rows",
        lambda _session, _list_url, _page_num: (None, "login_required"),
    )

    rows, err = index_tail._fetch_rows_with_interactive_login(
        FakeSession(),
        "https://cafe.example/list",
        1,
        interactive_login=False,
        input_func=lambda prompt: prompts.append(prompt),
    )

    assert rows is None
    assert err == "login_required"
    assert prompts == []


def test_collect_after_snapshot_continues_after_interactive_retry(monkeypatch):
    session = FakeSession()
    prompts = []
    calls = []

    def fake_fetch_rows(fetch_session, _list_url, page_num, **kwargs):
        calls.append((fetch_session, page_num, kwargs["interactive_login"]))
        return [{"article_id": 1, "url": "u", "title": "old", "posted_at": None}], None

    monkeypatch.setattr(index_tail, "_fetch_rows_with_interactive_login", fake_fetch_rows)

    total = index_tail._collect_after_snapshot(
        session,
        "https://cafe.example/list",
        min_id=2,
        interactive_login=True,
        input_func=lambda prompt: prompts.append(prompt),
    )

    assert total == 0
    assert calls == [(session, 1, True)]
    assert prompts == []


def test_main_noninteractive_does_not_call_wait_for_login(monkeypatch):
    session = FakeSession()
    wait_calls = []

    monkeypatch.setattr(index_tail, "init_db", lambda: None)
    monkeypatch.setattr(index_tail, "BrowserSession", lambda: session)
    monkeypatch.setattr(index_tail, "_load_latest_snapshot", lambda: {"snapshot_max_id": 9})
    monkeypatch.setattr(index_tail, "wait_for_login", lambda _page: wait_calls.append(_page))
    monkeypatch.setattr(index_tail, "_collect_after_snapshot", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(index_tail, "build_page_url", lambda url, page: f"{url}?page={page}")
    monkeypatch.setattr(index_tail.sys, "argv", ["index_tail.py", "https://cafe.example/list", "--collect-after-snapshot"])

    rc = index_tail.main()

    assert rc == 0
    assert wait_calls == []
    assert session.goto_calls == ["https://cafe.example/list?page=1"]


def test_main_interactive_calls_wait_for_login(monkeypatch):
    session = FakeSession()
    wait_calls = []

    monkeypatch.setattr(index_tail, "init_db", lambda: None)
    monkeypatch.setattr(index_tail, "BrowserSession", lambda: session)
    monkeypatch.setattr(index_tail, "_load_latest_snapshot", lambda: {"snapshot_max_id": 9})
    monkeypatch.setattr(index_tail, "wait_for_login", lambda page: wait_calls.append(page))
    monkeypatch.setattr(index_tail, "_collect_after_snapshot", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(index_tail, "build_page_url", lambda url, page: f"{url}?page={page}")
    monkeypatch.setattr(
        index_tail.sys,
        "argv",
        ["index_tail.py", "https://cafe.example/list", "--collect-after-snapshot", "--interactive-login"],
    )

    rc = index_tail.main()

    assert rc == 0
    assert wait_calls == [session.page]
    assert session.goto_calls == ["https://cafe.example/list?page=1"]
