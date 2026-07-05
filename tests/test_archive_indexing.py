import sys

sys.path.insert(0, "src")

import archive_indexing


class FakePage:
    def __init__(self, url, title="", content=""):
        self.url = url
        self._title = title
        self._content = content

    def title(self):
        return self._title

    def content(self):
        return self._content


def test_fetch_index_rows_uses_index_tail_primitives(monkeypatch):
    calls = []
    html = """
    <div class="article-board">
      <table><tbody><tr>
        <td class="td_article"><a href="/ArticleRead.nhn?clubid=1&articleid=123">title</a></td>
        <td class="td_date">2026.05.31</td>
      </tr></tbody></table>
    </div>
    """

    class FakeSession:
        def goto(self, url):
            calls.append(("goto", url))
            return "https://cafe.naver.com/list?page=1", None

        def get_frame_html(self):
            calls.append(("get_frame_html", None))
            return html, None

    monkeypatch.setattr(archive_indexing, "check_blocked", lambda _url, _html: None)

    rows, err = archive_indexing.fetch_index_rows(
        FakeSession(),
        "https://cafe.naver.com/list",
        1,
    )

    assert err is None
    assert calls == [
        ("goto", "https://cafe.naver.com/list?page=1"),
        ("get_frame_html", None),
    ]
    assert rows[0]["article_id"] == 123
    assert rows[0]["source_page"] == 1


def test_fetch_index_rows_rechecks_until_article_marker_appears():
    page_url = "https://cafe.naver.com/list?page=1"
    htmls = [
        '<html><script>window.e="NotLoggedInError"</script></html>',
        """
        <div class="article-board">
          <table><tbody><tr>
            <td class="td_article"><a href="/ArticleRead.nhn?clubid=1&articleid=124">ready</a></td>
          </tr></tbody></table>
        </div>
        """,
    ]

    class FakeSession:
        page = FakePage(page_url, title="")

        def __init__(self):
            self.html_calls = 0

        def goto(self, url):
            return url, "login_required"

        def get_frame_html(self):
            html = htmls[self.html_calls]
            self.html_calls += 1
            return html, None

    session = FakeSession()

    rows, err = archive_indexing.fetch_index_rows(
        session,
        "https://cafe.naver.com/list",
        1,
        sleeper=lambda _seconds: None,
    )

    assert err is None
    assert [row["article_id"] for row in rows] == [124]
    assert session.html_calls == 2


def test_fetch_index_rows_fails_immediately_on_definite_login_url(capsys):
    login_url = "https://nid.naver.com/nidlogin.login"

    class FakeSession:
        page = FakePage(login_url, title="Naver Login")

        def __init__(self):
            self.html_calls = 0

        def goto(self, url):
            return login_url, "login_required"

        def get_frame_html(self):
            self.html_calls += 1
            return '<form><input id="id"><input type="password"></form>', None

    session = FakeSession()

    rows, err = archive_indexing.fetch_index_rows(
        session,
        "https://cafe.naver.com/list",
        1,
        sleeper=lambda _seconds: None,
    )

    captured = capsys.readouterr()
    assert rows is None
    assert err == "login_required"
    assert session.html_calls == 1
    assert "redirected to login url" in captured.out
    assert "current_url_is_login=true" in captured.out


def test_fetch_index_rows_fails_immediately_on_password_input(capsys):
    page_url = "https://cafe.naver.com/list?page=1"

    class FakeSession:
        page = FakePage(page_url, title="Login")

        def __init__(self):
            self.html_calls = 0

        def goto(self, url):
            return url, None

        def get_frame_html(self):
            self.html_calls += 1
            return '<form><input id="id"><input type="password"></form>', None

    session = FakeSession()

    rows, err = archive_indexing.fetch_index_rows(
        session,
        "https://cafe.naver.com/list",
        1,
        sleeper=lambda _seconds: None,
    )

    captured = capsys.readouterr()
    assert rows is None
    assert err == "login_required"
    assert session.html_calls == 1
    assert "login form detected" in captured.out
    assert "password_input_found=true" in captured.out


def test_fetch_index_rows_rechecks_ambiguous_block_after_frame_html(monkeypatch):
    page_url = "https://cafe.naver.com/list?page=1"
    htmls = [
        '<html><script>window.e="NotLoggedInError"</script></html>',
        """
        <div class="article-board">
          <table><tbody><tr>
            <td class="td_article"><a href="/ArticleRead.nhn?clubid=1&articleid=125">ready</a></td>
          </tr></tbody></table>
        </div>
        """,
    ]

    class FakeSession:
        page = FakePage(page_url, title="")

        def __init__(self):
            self.html_calls = 0

        def goto(self, url):
            return url, None

        def get_frame_html(self):
            html = htmls[self.html_calls]
            self.html_calls += 1
            return html, None

    session = FakeSession()

    rows, err = archive_indexing.fetch_index_rows(
        session,
        "https://cafe.naver.com/list",
        1,
        sleeper=lambda _seconds: None,
    )

    assert err is None
    assert [row["article_id"] for row in rows] == [125]
    assert session.html_calls == 2


def test_fetch_index_rows_fails_after_repeated_login_marker_without_sensitive_dump(capsys):
    page_url = "https://cafe.naver.com/list?page=1"
    html = '<html><script>window.e="NotLoggedInError"</script><div>cookie=session-secret</div></html>'

    class FakeSession:
        page = FakePage(page_url, title="")

        def __init__(self):
            self.html_calls = 0

        def goto(self, url):
            return url, None

        def get_frame_html(self):
            self.html_calls += 1
            return html, None

    session = FakeSession()

    rows, err = archive_indexing.fetch_index_rows(
        session,
        "https://cafe.naver.com/list",
        1,
        sleeper=lambda _seconds: None,
    )

    captured = capsys.readouterr()
    assert rows is None
    assert err == "login_required"
    assert session.html_calls == 3
    assert "article_markers_found=false" in captured.out
    assert "login_markers_found=true" in captured.out
    assert "password_input_found=false" in captured.out
    assert "current_url_is_login=false" in captured.out
    assert "cookie" not in captured.out.lower()
    assert "session-secret" not in captured.out
    assert "<html" not in captured.out


def test_collect_index_rows_is_bounded_and_sleeps_between_pages(monkeypatch):
    calls = []
    sleeps = []

    def fake_fetch_rows(_session, _list_url, page_num, **_kwargs):
        calls.append(page_num)
        return [
            {"article_id": page_num * 10 + 1, "url": f"mock://{page_num}/1"},
            {"article_id": page_num * 10 + 2, "url": f"mock://{page_num}/2"},
        ], None

    monkeypatch.setattr(archive_indexing, "fetch_index_rows", fake_fetch_rows)

    rows = archive_indexing.collect_index_rows(
        object(),
        "https://example.test/list",
        limit=3,
        page_limit=5,
        delay_seconds=0.5,
        sleeper=sleeps.append,
    )

    assert [row["article_id"] for row in rows] == [11, 12, 21]
    assert calls == [1, 2]
    assert sleeps == [0.5]


def test_collect_index_rows_raises_on_list_page_error(monkeypatch):
    monkeypatch.setattr(
        archive_indexing,
        "fetch_index_rows",
        lambda _session, _list_url, _page_num, **_kwargs: (None, "login_required"),
    )

    try:
        archive_indexing.collect_index_rows(
            object(),
            "https://example.test/list",
            limit=1,
            page_limit=1,
            delay_seconds=0,
            sleeper=lambda _seconds: None,
        )
    except RuntimeError as exc:
        assert str(exc) == "list page 1 failed: login_required"
    else:
        raise AssertionError("expected RuntimeError")


def test_fetch_index_rows_preserves_login_required_over_empty_retry():
    """goto가 login_required를 준 뒤 빈 셸(마커 없음)이 와도 사유를 None으로 덮지 않는다.

    덮으면 ([], None)으로 반환돼 차단이 '빈 페이지 성공'으로 위장된다(조용한 0건).
    """

    class _EmptyShellSession:
        page = FakePage("https://cafe.naver.com/list?page=1", title="")

        def goto(self, url):
            return url, "login_required"

        def get_frame_html(self):
            return "<html><body><div>empty</div></body></html>", None

    rows, err = archive_indexing.fetch_index_rows(
        _EmptyShellSession(),
        "https://cafe.naver.com/list",
        1,
        sleeper=lambda _seconds: None,
    )

    assert rows is None
    assert err == "login_required"
