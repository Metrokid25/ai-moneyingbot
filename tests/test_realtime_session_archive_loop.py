import subprocess
import sys
from datetime import datetime
from pathlib import Path


SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import batch_recollect
import index_tail_realtime
import run_daily_archive_loop as archive_loop


class FakeSession:
    def __init__(self):
        self.page = object()
        self.closed = False
        self.close_count = 0
        self.goto_calls = []

    def goto(self, url):
        self.goto_calls.append(url)
        return url, None

    def close(self):
        self.closed = True
        self.close_count += 1


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


def _loop_config(tmp_path, **overrides):
    values = {
        "list_url": "https://example.test/list",
        "max_runs": 1,
        "duration_hours": 24,
        "interval_seconds": 1,
        "market_schedule": False,
        "realtime_index": True,
        "log_dir": tmp_path / "logs",
        "status_file": tmp_path / "state" / "archive_loop_status.json",
        "lock_file": tmp_path / "state" / "archive_loop.lock",
        "db_file": tmp_path / "data" / "archive.db",
    }
    values.update(overrides)
    return archive_loop.LoopConfig(**values)


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
    assert "[archive_loop] step 1/2: realtime title collection started" in result.stdout
    assert "[archive_loop] title collection finished: saved_delta=0 latest_id=-" in result.stdout
    assert "[archive_loop] step 2/2: body collection started" in result.stdout
    assert "[archive_loop] body collection finished" in result.stdout
    assert "[archive_loop] cycle 1 finished: returncode=0 saved_delta=0 latest_id=-" in result.stdout
    assert "index_tail_realtime.py" in result.stdout
    assert "batch_recollect.py" in result.stdout


def test_market_realtime_loop_reuses_one_session_across_cycles(monkeypatch, tmp_path):
    session = FakeSession()
    seen = []
    slept = []
    monkeypatch.setattr(archive_loop, "readonly_archive_summary", _archive_summary)

    def fake_index(_list_url, passed_session, **_kwargs):
        seen.append(("index", passed_session, passed_session.closed))
        print("[index_tail] complete")
        return 0

    def fake_batch(*, session):
        seen.append(("batch", session, session.closed))
        print("[batch] complete")
        return 0

    config = _loop_config(
        tmp_path,
        market_schedule=True,
        realtime_index=True,
        max_runs=2,
    )

    rc = archive_loop.run_loop(
        config,
        sleeper=slept.append,
        clock=lambda: datetime(2026, 6, 2, 9, 0, 0),
        realtime_browser_session_factory=lambda: session,
        realtime_index_runner=fake_index,
        batch_recollect_runner=fake_batch,
    )

    assert rc == 0
    assert slept == [300]
    assert seen == [
        ("index", session, False),
        ("batch", session, False),
        ("index", session, False),
        ("batch", session, False),
    ]
    assert session.closed is True
    assert session.close_count == 1


def test_market_realtime_interactive_login_prepares_before_inactive_skip(monkeypatch, tmp_path, capsys):
    session = FakeSession()
    enter_waits = []
    monkeypatch.setattr(archive_loop, "readonly_archive_summary", _archive_summary)

    config = _loop_config(
        tmp_path,
        market_schedule=True,
        realtime_index=True,
        interactive_login=True,
        max_runs=1,
    )

    rc = archive_loop.run_loop(
        config,
        sleeper=lambda _seconds: None,
        clock=lambda: datetime(2026, 6, 2, 23, 30, 0),
        realtime_browser_session_factory=lambda: session,
        realtime_index_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("title collection should not run while market schedule is inactive")
        ),
        batch_recollect_runner=lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("body collection should not run while market schedule is inactive")
        ),
        interactive_login_enter_waiter=lambda: enter_waits.append("enter"),
    )

    out = capsys.readouterr().out
    assert rc == 0
    # 2026-07-02: 로그인 준비는 (빈 SPA 셸이 되는) 목록 페이지 대신 네이버 로그인 페이지를 연다
    from member_api import NAVER_LOGIN_URL

    assert session.goto_calls == [NAVER_LOGIN_URL]
    assert enter_waits == ["enter"]
    assert out.index("[archive_loop] interactive login preparation started") < out.index(
        "[archive_loop] market schedule inactive: market-closed-23-06"
    )
    assert "[archive_loop] opening login/check page" in out
    assert "[LOGIN] 브라우저에서 네이버 로그인을 완료한 뒤, 이 PowerShell 창에서 엔터를 눌러주세요." in out
    assert "[LOGIN] 엔터 입력 대기 중..." in out
    assert "[archive_loop] interactive login preparation finished" in out
    assert session.closed is True
    assert session.close_count == 1


def test_market_realtime_interactive_login_reuses_prepared_session_when_active(monkeypatch, tmp_path):
    session = FakeSession()
    seen = []
    monkeypatch.setattr(archive_loop, "readonly_archive_summary", _archive_summary)

    def fake_index(_list_url, passed_session, **_kwargs):
        seen.append(("index", passed_session, list(passed_session.goto_calls), passed_session.closed))
        print("[index_tail] complete")
        return 0

    def fake_batch(*, session):
        seen.append(("batch", session, list(session.goto_calls), session.closed))
        print("[batch] complete")
        return 0

    config = _loop_config(
        tmp_path,
        market_schedule=True,
        realtime_index=True,
        interactive_login=True,
        max_runs=1,
    )

    rc = archive_loop.run_loop(
        config,
        sleeper=lambda _seconds: None,
        clock=lambda: datetime(2026, 6, 2, 9, 0, 0),
        realtime_browser_session_factory=lambda: session,
        realtime_index_runner=fake_index,
        batch_recollect_runner=fake_batch,
        interactive_login_enter_waiter=lambda: None,
    )

    from member_api import NAVER_LOGIN_URL

    assert rc == 0
    # 2026-07-02: 로그인 준비가 네이버 로그인 페이지를 연다 (목록 페이지 대신)
    assert session.goto_calls == [NAVER_LOGIN_URL]
    assert seen == [
        ("index", session, [NAVER_LOGIN_URL], False),
        ("batch", session, [NAVER_LOGIN_URL], False),
    ]
    assert session.closed is True
    assert session.close_count == 1


def test_single_realtime_run_closes_session_after_cycle(monkeypatch, tmp_path):
    session = FakeSession()
    seen = []
    monkeypatch.setattr(archive_loop, "readonly_archive_summary", _archive_summary)

    def fake_index(_list_url, passed_session, **_kwargs):
        seen.append(("index", passed_session, passed_session.closed))
        print("[index_tail] complete")
        return 0

    def fake_batch(*, session):
        seen.append(("batch", session, session.closed))
        print("[batch] complete")
        return 0

    config = _loop_config(tmp_path, realtime_index=True, max_runs=1)

    result = archive_loop.run_once_realtime_session(
        config,
        1,
        browser_session_factory=lambda: session,
        realtime_index_runner=fake_index,
        batch_recollect_runner=fake_batch,
    )

    assert result.returncode == 0
    assert seen == [
        ("index", session, False),
        ("batch", session, False),
    ]
    assert session.closed is True
    assert session.close_count == 1


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


def test_batch_recollect_prints_login_wait_prompt_when_login_required(monkeypatch, capsys):
    class LoginSession(FakeSession):
        def goto(self, url):
            self.goto_calls.append(url)
            return url, "login_required"

    session = LoginSession()

    monkeypatch.setattr(batch_recollect, "get_articles_by_status", lambda _status: [FakeArticle()])
    monkeypatch.setattr(batch_recollect, "get_conn", lambda: FakeConn())
    monkeypatch.setattr(batch_recollect, "_open_logfile", lambda: (Path("test.log"), FakeLog()))
    monkeypatch.setattr(batch_recollect, "_write_log_header", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(batch_recollect, "_write_final_report", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(batch_recollect, "_print_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(batch_recollect, "_print_error_reason_dist", lambda: None)
    monkeypatch.setattr(batch_recollect, "wait_for_login", lambda _page: None)
    monkeypatch.setattr(batch_recollect.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(batch_recollect, "get_article_by_id", lambda _aid: FakeCollectedArticle())
    monkeypatch.setattr(
        batch_recollect,
        "collect_body",
        lambda *_args, **_kwargs: (batch_recollect.Status.BODY_COLLECTED, None),
    )

    rc = batch_recollect.run_batch_recollect(session=session)

    out = capsys.readouterr().out
    assert rc == 0
    assert "[LOGIN] 브라우저에서 로그인을 완료한 뒤, 이 PowerShell 창에서 엔터를 눌러주세요." in out
    assert "[LOGIN] 엔터 입력 대기 중..." in out


def test_realtime_index_prints_login_wait_prompt_when_login_required(monkeypatch, capsys):
    class LoginSession(FakeSession):
        def goto(self, url):
            self.goto_calls.append(url)
            return url, "login_required"

    session = LoginSession()

    monkeypatch.setattr(index_tail_realtime, "init_db", lambda: None)
    monkeypatch.setattr(
        index_tail_realtime,
        "_load_latest_snapshot",
        lambda: {"snapshot_max_id": 100},
    )
    monkeypatch.setattr(index_tail_realtime, "wait_for_login", lambda _page: None)
    monkeypatch.setattr(index_tail_realtime, "_collect_after_snapshot", lambda *_args, **_kwargs: (0, None))

    rc = index_tail_realtime.run_realtime_index(
        "https://example.test/list",
        session,
        interactive_login=True,
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "[LOGIN] 브라우저에서 로그인을 완료한 뒤, 이 PowerShell 창에서 엔터를 눌러주세요." in out
    assert "[LOGIN] 엔터 입력 대기 중..." in out


def test_print_run_summary_does_not_replay_stdout(capsys):
    result = archive_loop.RunResult(
        run_number=1,
        started_at=datetime(2026, 6, 2, 9, 0, 0),
        finished_at=datetime(2026, 6, 2, 9, 1, 0),
        returncode=0,
        stdout="[LOGIN] 엔터 입력 대기 중...\n[batch] complete",
        stderr="",
        commands=[],
        before_article_count=10,
        after_article_count=12,
        latest_article_id=123,
    )

    archive_loop.print_run_summary(result, Path("logs/archive_loop/test.log"))

    out = capsys.readouterr().out
    assert "[archive_loop] run_number : 1" in out
    assert "[archive_loop] saved_delta: 2" in out
    assert "[archive_loop] latest_id : 123" in out
    assert "[archive_loop] log       : logs" in out
    assert "[archive_loop] stdout" not in out
    assert "[LOGIN] 엔터 입력 대기 중..." not in out
    assert "[archive_loop] stderr" not in out


def test_print_run_summary_prints_stderr_only_when_present(capsys):
    result = archive_loop.RunResult(
        run_number=1,
        started_at=datetime(2026, 6, 2, 9, 0, 0),
        finished_at=datetime(2026, 6, 2, 9, 1, 0),
        returncode=1,
        stdout="normal output",
        stderr="error output",
        commands=[],
        before_article_count=10,
        after_article_count=10,
        latest_article_id=123,
    )

    archive_loop.print_run_summary(result, Path("logs/archive_loop/test.log"))

    out = capsys.readouterr().out
    assert "[archive_loop] stdout" not in out
    assert "[archive_loop] stderr    : error output" in out


def test_batch_recollect_noninteractive_stops_cleanly_when_logged_out(monkeypatch):
    """무인(interactive=False): 로그아웃 확정 시 콘솔 Enter 대기 없이 서킷브레이커로 중단(rc=2)."""
    session = FakeSession()
    wait_calls = []

    monkeypatch.setattr(batch_recollect, "get_articles_by_status", lambda _status: [FakeArticle()])
    monkeypatch.setattr(batch_recollect, "get_conn", lambda: FakeConn())
    monkeypatch.setattr(batch_recollect, "_open_logfile", lambda: (Path("test.log"), FakeLog()))
    monkeypatch.setattr(batch_recollect, "_write_log_header", lambda *_a, **_k: None)
    monkeypatch.setattr(batch_recollect, "_write_final_report", lambda *_a, **_k: None)
    monkeypatch.setattr(batch_recollect, "_print_summary", lambda *_a, **_k: None)
    monkeypatch.setattr(batch_recollect, "_print_error_reason_dist", lambda: None)
    monkeypatch.setattr(batch_recollect, "wait_for_login", lambda _page: wait_calls.append(1))
    monkeypatch.setattr(
        batch_recollect,
        "check_member_login",
        lambda *_a, **_k: (False, "login_required: member_api code=0004"),
    )
    monkeypatch.setattr(batch_recollect.time, "sleep", lambda _s: None)
    monkeypatch.setattr(batch_recollect, "get_article_by_id", lambda _aid: FakeCollectedArticle())
    monkeypatch.setattr(
        batch_recollect,
        "collect_body",
        lambda *_a, **_k: (batch_recollect.Status.BODY_COLLECTED, None),
    )

    rc = batch_recollect.run_batch_recollect(session=session, interactive=False)

    assert rc == 2  # CircuitBreakerTripped → 깔끔한 중단
    assert wait_calls == []  # 무인: wait_for_login(콘솔 Enter 대기) 절대 호출 안 함


def test_alert_on_session_expiry_sends_via_notify_telegram(tmp_path, monkeypatch):
    """루프 배선: 멤버 API 프로브 False 확정 → notify_telegram(재사용)으로 [Archive] 알림."""
    import member_api
    import notify_telegram

    config = _loop_config(
        tmp_path,
        list_url="https://cafe.naver.com/ca-fe/cafes/29082876/members/ABC_key-1",
    )
    monkeypatch.setattr(
        member_api, "check_member_login",
        lambda *_a, **_k: (False, "login_required: member_api code=0004 (로그인하지 않았습니다)"),
    )
    sent = []
    monkeypatch.setattr(notify_telegram, "send_telegram", lambda text, **_k: (sent.append(text) or True))

    res = archive_loop.alert_on_session_expiry(config, object(), datetime(2026, 7, 6, 9, 0, 0))

    assert res["expired"] is True and res["alerted"] is True
    assert len(sent) == 1
    assert sent[0].splitlines()[0] == "[Archive] 세션 만료 감지"


def test_alert_on_session_expiry_skips_non_member_url(tmp_path, monkeypatch):
    """멤버 목록 URL이 아니면 프로브/알림 없이 스킵(오탐 방지)."""
    import notify_telegram

    config = _loop_config(tmp_path, list_url="https://cafe.naver.com/some/board")
    sent = []
    monkeypatch.setattr(notify_telegram, "send_telegram", lambda text, **_k: (sent.append(text) or True))

    res = archive_loop.alert_on_session_expiry(config, object(), datetime(2026, 7, 6, 9, 0, 0))

    assert res["alerted"] is False
    assert sent == []
