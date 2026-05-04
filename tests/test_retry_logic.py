"""tests/test_retry_logic.py — retry logic unit tests.

DB 함수는 in-process temp DB로 직접 검증.
collect_body는 BrowserSession + parse_article 을 mock 처리.
"""
import sqlite3
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, "src")

import db as db_module
from db import (
    MAX_RETRY_ATTEMPTS,
    get_article_by_id,
    get_attempt_count,
    get_conn,
    init_db,
    record_attempt_start,
    record_body_collected,
    record_permanent_failure,
    record_transient_failure,
    reset_to_indexed,
    upsert_article,
)
from models import Article, Status


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    """모든 테스트에서 임시 DB 사용."""
    test_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", test_path)
    init_db()
    return test_path


def _insert_indexed(article_id: int, attempt_count: int = 0) -> None:
    art = Article(
        article_id=article_id,
        url=f"https://cafe.naver.com/test/{article_id}",
        status=Status.INDEXED,
    )
    upsert_article(art)
    if attempt_count:
        conn = get_conn()
        conn.execute(
            "UPDATE articles SET attempt_count=? WHERE article_id=?",
            (attempt_count, article_id),
        )
        conn.commit()
        conn.close()


def _query(article_id: int) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT status, attempt_count, last_error_reason FROM articles WHERE article_id=?",
        (article_id,),
    ).fetchone()
    conn.close()
    return {"status": row[0], "attempt_count": row[1], "last_error_reason": row[2]}


# ── DB 함수 단위 테스트 ───────────────────────────────────────────────────────

def test_record_attempt_start_increments():
    _insert_indexed(1)
    conn = get_conn()
    record_attempt_start(conn, 1)
    conn.commit()
    assert get_attempt_count(conn, 1) == 1
    record_attempt_start(conn, 1)
    conn.commit()
    assert get_attempt_count(conn, 1) == 2
    conn.close()


def test_record_transient_failure_keeps_indexed():
    _insert_indexed(2)
    conn = get_conn()
    record_attempt_start(conn, 2)
    record_transient_failure(conn, 2, "timeout: selector not found in 10s")
    conn.commit()
    conn.close()
    r = _query(2)
    assert r["status"] == Status.INDEXED
    assert r["last_error_reason"] == "timeout: selector not found in 10s"
    assert r["attempt_count"] == 1


def test_record_permanent_failure_sets_body_failed():
    _insert_indexed(3)
    conn = get_conn()
    record_attempt_start(conn, 3)
    record_permanent_failure(conn, 3, "article deleted/not found")
    conn.commit()
    conn.close()
    r = _query(3)
    assert r["status"] == Status.BODY_FAILED
    assert r["last_error_reason"] == "article deleted/not found"


def test_record_body_collected_clears_error_reason():
    _insert_indexed(4)
    conn = get_conn()
    record_attempt_start(conn, 4)
    record_transient_failure(conn, 4, "some transient reason")
    record_attempt_start(conn, 4)
    record_body_collected(conn, 4, "<html>body</html>", "clean text content")
    conn.commit()
    conn.close()
    r = _query(4)
    assert r["status"] == Status.BODY_COLLECTED
    assert r["last_error_reason"] is None


def test_reset_to_indexed_clears_attempt_count():
    _insert_indexed(5, attempt_count=3)
    art = get_article_by_id(5)
    art_obj = Article(
        article_id=5, url=art.url, status=Status.BODY_FAILED
    )
    upsert_article(art_obj)
    conn = get_conn()
    reset_to_indexed(conn, 5, "force recollect from BODY_FAILED")
    conn.commit()
    conn.close()
    r = _query(5)
    assert r["status"] == Status.INDEXED
    assert r["attempt_count"] == 0
    assert r["last_error_reason"] == "force recollect from BODY_FAILED"


# ── collect_body 통합 테스트 (BrowserSession mock) ───────────────────────────

def _make_frame(inner_html="<p>충분히 긴 본문 텍스트 입니다 검증용 최소 길이를 넘기기 위한 내용</p>",
                full_html=None):
    frame = MagicMock()
    frame.url = "https://cafe.naver.com/test/1"
    frame.name = "cafe_main"
    frame.inner_html.return_value = inner_html
    frame.content.return_value = full_html or f"<html><body>{inner_html}</body></html>"
    frame.wait_for_selector.return_value = None
    return frame


def _make_session(goto_err=None, frame=None):
    session = MagicMock()
    session.goto.return_value = ("https://cafe.naver.com/test/1", goto_err)
    mock_frame = frame or _make_frame()
    session.page.frame.return_value = mock_frame
    session.page.frames = [mock_frame]
    session.page.wait_for_timeout.return_value = None
    return session, mock_frame


LONG_CLEAN_TEXT = "충분히 긴 본문 " * 20  # > 50자


def test_collect_body_success():
    _insert_indexed(10)
    session, frame = _make_session()
    with patch("collector.parse_article", return_value=("title", "2026-01-01", LONG_CLEAN_TEXT, "<html/>", False, True)):
        from collector import collect_body
        result, _ = collect_body(10, session=session)
    assert result == Status.BODY_COLLECTED
    r = _query(10)
    assert r["status"] == Status.BODY_COLLECTED
    assert r["attempt_count"] == 1
    assert r["last_error_reason"] is None


def test_collect_body_transient_increments_attempt():
    _insert_indexed(20)
    session, frame = _make_session()
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    frame.wait_for_selector.side_effect = PlaywrightTimeoutError("timeout")

    from collector import collect_body
    result, _ = collect_body(20, session=session)
    assert result == Status.INDEXED
    r = _query(20)
    assert r["status"] == Status.INDEXED
    assert r["attempt_count"] == 1
    assert "timeout" in r["last_error_reason"]


def test_collect_body_5th_failure_demotes():
    _insert_indexed(30, attempt_count=4)  # 4번 실패 이력
    session, frame = _make_session()
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    frame.wait_for_selector.side_effect = PlaywrightTimeoutError("timeout")

    from collector import collect_body
    collect_body(30, session=session)
    r = _query(30)
    assert r["status"] == Status.BODY_FAILED
    assert r["attempt_count"] == 5
    assert "exceeded max retries" in r["last_error_reason"]
    assert "attempts: 5" in r["last_error_reason"]


def test_preflight_demotes_when_count_already_at_max():
    """이전 실행이 중단돼 count=5이지만 status=INDEXED인 경우 pre-flight 강등."""
    _insert_indexed(31, attempt_count=5)
    session, _ = _make_session()

    from collector import collect_body
    result, _ = collect_body(31, session=session)
    assert result == Status.BODY_FAILED
    r = _query(31)
    assert r["status"] == Status.BODY_FAILED
    assert "accumulated attempts: 5" in r["last_error_reason"]
    # BrowserSession.goto가 호출되지 않아야 함 (pre-flight에서 early return)
    session.goto.assert_not_called()


def test_collect_body_parse_error_permanent_fail():
    _insert_indexed(40)
    session, _ = _make_session()
    with patch("collector.parse_article", side_effect=Exception("malformed html")):
        from collector import collect_body
        result, _ = collect_body(40, session=session)
    assert result == Status.BODY_FAILED
    r = _query(40)
    assert r["status"] == Status.BODY_FAILED
    assert r["attempt_count"] == 1
    assert "parse error" in r["last_error_reason"]
    assert "exceeded max retries" not in r["last_error_reason"]


def test_collect_body_force_resets_attempt_count_from_body_failed():
    _insert_indexed(50, attempt_count=3)
    conn = get_conn()
    conn.execute("UPDATE articles SET status='BODY_FAILED' WHERE article_id=50")
    conn.commit()
    conn.close()

    session, _ = _make_session()
    with patch("collector.parse_article", return_value=("t", "d", LONG_CLEAN_TEXT, "<html/>", False, True)):
        from collector import collect_body
        result, _ = collect_body(50, session=session, force=True)

    assert result == Status.BODY_COLLECTED
    r = _query(50)
    assert r["status"] == Status.BODY_COLLECTED
    # force → count=0 리셋 후 +1 = 1
    assert r["attempt_count"] == 1


def test_collect_body_force_resets_attempt_count_from_indexed():
    """Bug #4: force=True가 INDEXED 상태에서도 attempt_count를 0으로 리셋."""
    _insert_indexed(51, attempt_count=7)  # count가 쌓인 INDEXED (Bug #3 시나리오)

    session, _ = _make_session()
    with patch("collector.parse_article", return_value=("t", "d", LONG_CLEAN_TEXT, "<html/>", False, True)):
        from collector import collect_body
        result, _ = collect_body(51, session=session, force=True)

    assert result == Status.BODY_COLLECTED
    r = _query(51)
    assert r["status"] == Status.BODY_COLLECTED
    assert r["attempt_count"] == 1  # 0 리셋 후 +1


def test_collect_body_success_clears_last_error_reason():
    _insert_indexed(60)
    conn = get_conn()
    conn.execute("UPDATE articles SET last_error_reason='old error' WHERE article_id=60")
    conn.commit()
    conn.close()

    session, _ = _make_session()
    with patch("collector.parse_article", return_value=("t", "d", LONG_CLEAN_TEXT, "<html/>", False, True)):
        from collector import collect_body
        collect_body(60, session=session)

    r = _query(60)
    assert r["last_error_reason"] is None


# ── DEV_MODE guard 테스트 ─────────────────────────────────────────────────────

def test_5th_simulate_fail_timeout_demotes_immediately(monkeypatch):
    """Bug #3 보강: 5번째 simulate-fail timeout이 같은 실행 내에서 즉시 BODY_FAILED 강등.

    pre-flight(count=5)와 다르게, count=4에서 시작해 attempt_count가 5가 된 직후
    _handle_transient → _check_and_demote 경로로 강등이 이뤄지는지 검증.
    """
    monkeypatch.setenv("DEV_MODE", "1")
    _insert_indexed(120, attempt_count=4)  # 4회 이력, pre-flight 통과 대상
    session, _ = _make_session()

    from collector import collect_body
    result = collect_body(120, session=session, simulate_fail="timeout")

    # 반환값은 INDEXED일 수 있으나 DB 상태는 즉시 BODY_FAILED여야 함 (pre-flight가 아닌 in-flight 강등)
    r = _query(120)
    assert r["status"] == Status.BODY_FAILED, "5번째 실패 직후 즉시 BODY_FAILED로 강등돼야 함"
    assert r["attempt_count"] == 5
    assert "exceeded max retries" in r["last_error_reason"]
    assert "last:" in r["last_error_reason"]
    assert "attempts: 5" in r["last_error_reason"]


def test_simulate_fail_requires_dev_mode(monkeypatch):
    monkeypatch.delenv("DEV_MODE", raising=False)
    _insert_indexed(70)
    session, _ = _make_session()

    from collector import collect_body
    with pytest.raises(SystemExit, match="DEV_MODE"):
        collect_body(70, session=session, simulate_fail="timeout")


def test_simulate_fail_timeout_with_dev_mode(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "1")
    _insert_indexed(80)
    session, frame = _make_session()
    # simulate timeout: PlaywrightTimeoutError raised before wait_for_selector
    from collector import collect_body
    result, _ = collect_body(80, session=session, simulate_fail="timeout")
    assert result == Status.INDEXED
    r = _query(80)
    assert r["status"] == Status.INDEXED
    assert "timeout" in r["last_error_reason"]


def test_simulate_fail_empty_with_dev_mode(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "1")
    _insert_indexed(90)
    session, frame = _make_session()
    frame.inner_html.return_value = "<p>real content</p>"

    from collector import collect_body
    result, _ = collect_body(90, session=session, simulate_fail="empty")
    assert result == Status.INDEXED
    r = _query(90)
    assert "empty inner_html" in r["last_error_reason"]


def test_simulate_fail_navigation_with_dev_mode(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "1")
    _insert_indexed(100)
    session, _ = _make_session()

    from collector import collect_body
    result, _ = collect_body(100, session=session, simulate_fail="navigation")
    assert result == Status.INDEXED
    r = _query(100)
    assert "navigation" in r["last_error_reason"]


def test_simulate_fail_session_with_dev_mode(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "1")
    _insert_indexed(110)
    session, frame = _make_session()
    frame.inner_html.return_value = "<p>충분히 긴 본문 텍스트 입니다 여러 단어가 있어야 합니다</p>"

    from collector import collect_body
    result, _ = collect_body(110, session=session, simulate_fail="session")
    assert result == Status.INDEXED
    r = _query(110)
    assert "session expired" in r["last_error_reason"]


# ── 신규 테스트 (B-1~B-5) ─────────────────────────────────────────────────────

def test_collect_body_image_only_body_succeeds():
    """이미지만 있는 글(clean_text 없음, has_media=True) → BODY_COLLECTED."""
    _insert_indexed(200)
    session, frame = _make_session()
    frame.inner_html.return_value = "<img src='x.jpg'>"
    frame.content.return_value = "<html><body><img src='x.jpg'></body></html>"
    with patch("collector.parse_article", return_value=("", None, "", "<img src='x.jpg'>", True, True)):
        from collector import collect_body
        result, _ = collect_body(200, session=session)
    assert result == Status.BODY_COLLECTED
    conn = get_conn()
    row = conn.execute("SELECT raw_html FROM articles WHERE article_id=200").fetchone()
    conn.close()
    assert row[0] is not None


def test_collect_body_short_text_succeeds():
    """50자 미만 짧은 텍스트(2자) → BODY_COLLECTED (기존 MIN_BODY_LENGTH=50 제거 검증)."""
    _insert_indexed(201)
    session, frame = _make_session()
    with patch("collector.parse_article", return_value=(None, None, "상승", "<p>상승</p>", False, True)):
        from collector import collect_body
        result, _ = collect_body(201, session=session)
    assert result == Status.BODY_COLLECTED
    conn = get_conn()
    row = conn.execute("SELECT clean_text FROM articles WHERE article_id=201").fetchone()
    conn.close()
    assert row[0] == "상승"


def test_collect_body_truly_empty_transient():
    """텍스트 없음 + 미디어 없음 → INDEXED transient, raw_html 보존."""
    _insert_indexed(202)
    session, frame = _make_session()
    with patch("collector.parse_article", return_value=(None, None, "", "", False, True)):
        from collector import collect_body
        result, _ = collect_body(202, session=session)
    assert result == Status.INDEXED
    r = _query(202)
    assert r["last_error_reason"] == "truly empty: no text, no media"
    conn = get_conn()
    row = conn.execute("SELECT raw_html FROM articles WHERE article_id=202").fetchone()
    conn.close()
    assert row[0] is not None


def test_record_transient_failure_preserves_raw_html_when_none():
    """raw_html=None 호출 시 기존 raw_html 유지 (COALESCE 동작)."""
    _insert_indexed(210)
    conn = get_conn()
    conn.execute("UPDATE articles SET raw_html='<p>existing</p>' WHERE article_id=210")
    conn.commit()
    record_transient_failure(conn, 210, "some reason", raw_html=None)
    conn.commit()
    row = conn.execute("SELECT raw_html FROM articles WHERE article_id=210").fetchone()
    conn.close()
    assert row[0] == "<p>existing</p>"


def test_record_transient_failure_stores_raw_html_when_provided():
    """raw_html 값 제공 시 신규 값 저장."""
    _insert_indexed(211)
    conn = get_conn()
    record_transient_failure(conn, 211, "some reason", raw_html="<p>new</p>")
    conn.commit()
    row = conn.execute("SELECT raw_html FROM articles WHERE article_id=211").fetchone()
    conn.close()
    assert row[0] == "<p>new</p>"


# ── Path 0: ContentRenderer 미로드 테스트 ─────────────────────────────────────

def test_collect_body_content_renderer_not_loaded_transient():
    """T1: article_viewer 있으나 ContentRenderer 미로드 → INDEXED transient."""
    _insert_indexed(300)
    session, frame = _make_session()
    with patch("collector.parse_article", return_value=("", None, "", "<div class='article_viewer'><img src='loading.gif'></div>", False, False)):
        from collector import collect_body
        result, _ = collect_body(300, session=session)
    assert result == Status.INDEXED
    r = _query(300)
    assert r["status"] == Status.INDEXED
    assert r["last_error_reason"] == "content_renderer_not_loaded"


def test_collect_body_renderer_loaded_media_only_succeeds():
    """T2: ContentRenderer 로드 + 텍스트 없음 + 미디어 있음 → BODY_COLLECTED (Path 2)."""
    _insert_indexed(301)
    session, frame = _make_session()
    with patch("collector.parse_article", return_value=("", None, "", "<div class='ContentRenderer'><img src='photo.jpg'></div>", True, True)):
        from collector import collect_body
        result, _ = collect_body(301, session=session)
    assert result == Status.BODY_COLLECTED
    r = _query(301)
    assert r["status"] == Status.BODY_COLLECTED


def test_collect_body_renderer_loaded_truly_empty_transient():
    """T3: ContentRenderer 로드 + 텍스트 없음 + 미디어 없음 → INDEXED transient (Path 1)."""
    _insert_indexed(302)
    session, frame = _make_session()
    with patch("collector.parse_article", return_value=("", None, "", "", False, True)):
        from collector import collect_body
        result, _ = collect_body(302, session=session)
    assert result == Status.INDEXED
    r = _query(302)
    assert r["status"] == Status.INDEXED
    assert r["last_error_reason"] == "truly empty: no text, no media"
