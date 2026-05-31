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
