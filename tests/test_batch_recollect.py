import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import batch_recollect


class FakeArticle:
    article_id = 123


def test_batch_login_check_uses_article_list_page_one(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.page = object()
            self.goto_calls = []

        def goto(self, url):
            self.goto_calls.append(url)
            return url, None

        def close(self):
            pass

    sessions = []

    def fake_browser_session():
        session = FakeSession()
        sessions.append(session)
        return session

    monkeypatch.setattr(batch_recollect, "BrowserSession", fake_browser_session)
    monkeypatch.setattr(batch_recollect, "wait_for_login", lambda _page: None)
    monkeypatch.setattr(batch_recollect, "get_articles_by_status", lambda _status: [FakeArticle()])
    monkeypatch.setattr(batch_recollect, "_open_logfile", lambda: (Path("test.log"), FakeLog()))
    monkeypatch.setattr(batch_recollect, "_write_log_header", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(batch_recollect, "_write_final_report", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(batch_recollect, "_print_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(batch_recollect, "_print_error_reason_dist", lambda: None)
    monkeypatch.setattr(batch_recollect, "get_article_by_id", lambda _aid: None)
    monkeypatch.setattr(batch_recollect, "collect_body", lambda *_args, **_kwargs: ("INDEXED", None))
    monkeypatch.setattr(batch_recollect.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(batch_recollect.sys, "argv", ["batch_recollect.py"])

    rc = batch_recollect.main()

    assert rc == 1
    assert sessions[0].goto_calls == [batch_recollect.CAFE_MEMBERS_LIST_URL]
    assert batch_recollect.CAFE_MEMBERS_LIST_URL.endswith("?page=1")


class FakeLog:
    def write(self, _text):
        pass

    def close(self):
        pass
