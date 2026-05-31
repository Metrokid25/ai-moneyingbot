import sys

sys.path.insert(0, "src")

import browser


class FakePage:
    def close(self):
        pass


class FakeContext:
    def __init__(self):
        self.page = FakePage()

    def new_page(self):
        return self.page

    def close(self):
        pass


class FakeChromium:
    def __init__(self, calls):
        self.calls = calls

    def launch_persistent_context(self, **kwargs):
        self.calls.append(("launch_persistent_context", kwargs))
        return FakeContext()

    def launch(self, **_kwargs):
        raise AssertionError("default BrowserSession should use persistent context")


class FakePlaywright:
    def __init__(self, calls):
        self.chromium = FakeChromium(calls)

    def stop(self):
        pass


class FakePlaywrightStarter:
    def __init__(self, calls):
        self.calls = calls

    def start(self):
        return FakePlaywright(self.calls)


def test_browser_session_uses_persistent_profile_by_default(tmp_path, monkeypatch):
    calls = []
    profile_dir = tmp_path / "browser_profile"
    monkeypatch.setattr(browser, "sync_playwright", lambda: FakePlaywrightStarter(calls))

    session = browser.BrowserSession(user_data_dir=profile_dir)
    session.close()

    assert profile_dir.exists()
    assert calls == [
        (
            "launch_persistent_context",
            {
                "user_data_dir": str(profile_dir),
                "headless": browser.HEADLESS,
            },
        )
    ]


def test_browser_session_accepts_headless_override(tmp_path, monkeypatch):
    calls = []
    profile_dir = tmp_path / "browser_profile"
    monkeypatch.setattr(browser, "sync_playwright", lambda: FakePlaywrightStarter(calls))

    session = browser.BrowserSession(user_data_dir=profile_dir, headless=False)
    session.close()

    assert calls == [
        (
            "launch_persistent_context",
            {
                "user_data_dir": str(profile_dir),
                "headless": False,
            },
        )
    ]


def test_not_logged_in_error_with_article_list_marker_is_not_login_required():
    html = """
    <html>
      <script>window.__ERROR__ = "NotLoggedInError";</script>
      <div class="article-board">
        <tbody><tr><td class="td_article"><a href="/ArticleRead.nhn?articleid=123">title</a></td></tr></tbody>
      </div>
    </html>
    """

    reason, detail = browser.detect_login_required("https://cafe.naver.com/f-e/cafes/1/members/x", html)

    assert reason is None
    assert detail == "article-list markers found"
    assert browser.check_blocked("https://cafe.naver.com/f-e/cafes/1/members/x", html) is None


def test_login_form_marker_is_login_required():
    html = """
    <form action="https://nid.naver.com/nidlogin.login">
      <input id="id" name="id">
      <input id="pw" name="pw" type="password">
    </form>
    """

    reason, detail = browser.detect_login_required("https://nid.naver.com/nidlogin.login", html)

    assert reason == "login_required"
    assert detail == "redirected to login url"


def test_not_logged_in_error_without_article_list_marker_is_login_required():
    html = '<div id="__next_error__">NotLoggedInError</div>'

    reason, detail = browser.detect_login_required("https://cafe.naver.com/f-e/cafes/1/members/x", html)

    assert reason == "login_required"
    assert detail == "no article-list markers found and login marker visible"


def test_login_detection_summary_exposes_safe_marker_booleans():
    html = '<form><input id="id"><input type="password"></form>'

    detection = browser.detect_login_state("https://cafe.naver.com/f-e/cafes/1/members/x", html)

    assert detection.reason == "login_required"
    summary = browser.format_login_detection_summary(detection)
    assert "article_markers_found=false" in summary
    assert "login_markers_found=true" in summary
    assert "password_input_found=true" in summary
    assert "current_url_is_login=false" in summary


def test_existing_block_markers_still_detected():
    captcha_signal = next(signal for reason, signal in browser._BLOCK_CONTENT if reason == "captcha")

    assert browser.check_blocked("https://cafe.naver.com/example", captcha_signal) == "captcha"
