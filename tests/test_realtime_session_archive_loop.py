import subprocess
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import batch_recollect
import run_daily_archive_loop as archive_loop


class FakeSession:
    def __init__(self):
        self.page = object()
        self.closed = False
        self.goto_calls = []

    def goto(self, url):
        self.goto_calls.append(url)
        return url, None

    def close(self):
        self.closed = True


class FakeLog:
    def write(self, _text):
        pass

    def close(self):
        pass


class FakeArticle:
    article_id = 123


class FakeCollectedArticle:
    status = batch_recollect.Status.BODY_COLLECTED
    clean_text = "body"


class FakeConn:
    def execute(self, *_args, **_kwargs):
        return self

    def fetchone(self):
        return [0]

    def close(self):
        pass


def _archive_summary(_db_file):
    return {"article_count": 0, "latest_article_id": None}


def test_default_run_once_keeps_subprocess_command_path(monkeypatch):
    calls = []
    monkeypatch.setattr(archive_loop, "readonly_archive_summary", _archive_summary)

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    config = archive_loop.LoopConfig(list_url="https://example.test/list")

    result = archive_loop.run_once(config, 1, runner=fake_runner)

    assert result.returncode == 0
    assert len(calls) == 2
    assert Path(calls[0][0][1]).name == "index_tail.py"
    assert Path(calls[1][0][1]).name == "batch_recollect.py"
    assert all(call[1]["capture_output"] is True for call in calls)


def test_realtime_session_run_uses_one_session_for_index_and_batch(monkeypatch):
    session = FakeSession()
    seen = []
    monkeypatch.setattr(archive_loop, "readonly_archive_summary", _archive_summary)

    def fake_index(list_url, passed_session, **kwargs):
        seen.append(("index", list_url, passed_session, kwargs))
        print("[index_tail] complete")
        return 0

    def fake_batch(*, session):
        seen.append(("batch", session))
        print("[batch] complete")
        return 0

    config = archive_loop.LoopConfig(
        list_url="https://example.test/list",
        realtime_index=True,
        interactive_login=True,
        stop_after_empty_pages=7,
    )

    result = archive_loop.run_once_realtime_session(
        config,
        1,
        browser_session_factory=lambda: session,
        realtime_index_runner=fake_index,
        batch_recollect_runner=fake_batch,
    )

    assert result.returncode == 0
    assert seen[0][0] == "index"
    assert seen[0][2] is session
    assert seen[0][3]["interactive_login"] is True
    assert seen[0][3]["stop_after_empty_pages"] == 7
    assert seen[1] == ("batch", session)
    assert session.closed is True
    assert "index_tail_realtime.py" in result.stdout
    assert "batch_recollect.py" in result.stdout


def test_batch_recollect_accepts_existing_session(monkeypatch):
    session = FakeSession()
    collect_sessions = []

    monkeypatch.setattr(batch_recollect, "get_articles_by_status", lambda _status: [FakeArticle()])
    monkeypatch.setattr(batch_recollect, "get_conn", lambda: FakeConn())
    monkeypatch.setattr(batch_recollect, "_open_logfile", lambda: (Path("test.log"), FakeLog()))
    monkeypatch.setattr(batch_recollect, "_write_log_header", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(batch_recollect, "_write_final_report", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(batch_recollect, "_print_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(batch_recollect, "_print_error_reason_dist", lambda: None)
    monkeypatch.setattr(batch_recollect, "wait_for_login", lambda _page: None)
    monkeypatch.setattr(batch_recollect.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(batch_recollect.random, "uniform", lambda _a, _b: 0)
    monkeypatch.setattr(batch_recollect, "get_article_by_id", lambda _aid: FakeCollectedArticle())

    def fake_collect_body(_aid, *, session, simulate_fail=None):
        collect_sessions.append(session)
        return batch_recollect.Status.BODY_COLLECTED, None

    monkeypatch.setattr(batch_recollect, "collect_body", fake_collect_body)

    rc = batch_recollect.run_batch_recollect(session=session)

    assert rc == 0
    assert collect_sessions == [session]
    assert session.closed is False
    assert session.goto_calls == [batch_recollect.CAFE_MEMBERS_LIST_URL]
