import inspect
import sys

import pytest


sys.path.insert(0, "scripts")

import index_tail


class FakeSession:
    pass


TRANSIENT = "member_api_request_failed: socket hang up"
BLOCK = "login_required: member_api code=0004 (로그인하지 않았습니다)"
ROWS = [
    {
        "article_id": 1234,
        "url": "https://example.test/1234",
        "title": "title",
        "posted_at": None,
    }
]


def _sequence_fetch(responses, calls):
    remaining = list(responses)

    def fake_fetch(_session, _list_url, page_num, **_kwargs):
        calls.append(page_num)
        return remaining.pop(0)

    return fake_fetch


def test_create_snapshot_retries_transient_error_on_same_page(monkeypatch, tmp_path):
    calls = []
    sleeps = []
    monkeypatch.setattr(
        index_tail,
        "_fetch_rows_with_interactive_login",
        _sequence_fetch([(None, TRANSIENT)] * 3 + [(ROWS, None)], calls),
    )
    monkeypatch.setattr(index_tail, "_sleep", lambda: sleeps.append(True))
    monkeypatch.setattr(index_tail, "_get_db_max_id", lambda: 1200)
    monkeypatch.setattr(index_tail, "_SNAPSHOT_DIR", tmp_path)

    snapshot = index_tail._create_snapshot(FakeSession(), "https://example.test/list")

    assert snapshot is not None
    assert snapshot["snapshot_max_id"] == 1234
    assert calls == [1, 1, 1, 1]
    assert len(sleeps) == 3
    assert len(list(tmp_path.glob("snapshot_*.json"))) == 1


def test_create_snapshot_does_not_retry_block_error(monkeypatch, tmp_path):
    calls = []
    sleeps = []
    monkeypatch.setattr(
        index_tail,
        "_fetch_rows_with_interactive_login",
        _sequence_fetch([(None, BLOCK)], calls),
    )
    monkeypatch.setattr(index_tail, "_sleep", lambda: sleeps.append(True))
    monkeypatch.setattr(index_tail, "_SNAPSHOT_DIR", tmp_path)

    assert index_tail._create_snapshot(FakeSession(), "https://example.test/list") is None
    assert calls == [1]
    assert sleeps == []
    assert list(tmp_path.iterdir()) == []


def test_find_tail_retries_transient_estimate_then_succeeds(monkeypatch):
    calls = []
    sleeps = []
    monkeypatch.setattr(
        index_tail,
        "_fetch_rows_with_interactive_login",
        _sequence_fetch(
            [(None, TRANSIENT), (None, TRANSIENT), (ROWS, None), ([], None)],
            calls,
        ),
    )
    monkeypatch.setattr(index_tail, "_sleep", lambda: sleeps.append(True))

    tail = index_tail.find_tail(FakeSession(), "https://example.test/list", 10)

    assert tail == 10
    assert calls == [10, 10, 10, 11]
    assert len(sleeps) == 3  # retry 2회 + 다음 페이지 이동 1회


def test_find_tail_does_not_retry_block_error(monkeypatch):
    calls = []
    monkeypatch.setattr(
        index_tail,
        "_fetch_rows_with_interactive_login",
        _sequence_fetch([(None, BLOCK)], calls),
    )
    monkeypatch.setattr(
        index_tail,
        "_sleep",
        lambda: (_ for _ in ()).throw(AssertionError("block errors must not sleep")),
    )

    assert index_tail.find_tail(FakeSession(), "https://example.test/list", 10) is None
    assert calls == [10]


def test_find_tail_does_not_return_last_good_after_forward_retry_exhaustion(monkeypatch):
    calls = []
    monkeypatch.setattr(
        index_tail,
        "_fetch_rows_with_interactive_login",
        _sequence_fetch([(ROWS, None)] + [(None, TRANSIENT)] * 4, calls),
    )
    monkeypatch.setattr(index_tail, "_sleep", lambda: None)

    assert index_tail.find_tail(FakeSession(), "https://example.test/list", 10) is None
    assert calls == [10, 11, 11, 11, 11]


def test_find_tail_does_not_skip_backward_page_after_retry_exhaustion(monkeypatch):
    calls = []
    monkeypatch.setattr(
        index_tail,
        "_fetch_rows_with_interactive_login",
        _sequence_fetch([([], None)] + [(None, TRANSIENT)] * 4, calls),
    )
    monkeypatch.setattr(index_tail, "_sleep", lambda: None)

    assert index_tail.find_tail(FakeSession(), "https://example.test/list", 10) is None
    assert calls == [10, 9, 9, 9, 9]


def test_manual_retry_helper_is_not_used_by_realtime_collection():
    source = inspect.getsource(index_tail._collect_after_snapshot)

    assert "_fetch_rows_for_manual_scan" not in source
    assert "_fetch_rows_with_interactive_login" in source


def test_default_estimate_recalculates_legacy_15_rows_for_api_20_rows():
    assert index_tail.LEGACY_ESTIMATE == 2828
    assert index_tail.LEGACY_PER_PAGE == 15
    assert index_tail.DEFAULT_PER_PAGE == 20
    assert index_tail.MEMBER_API_DEFAULT_ESTIMATE == 2121
    assert (
        index_tail.MEMBER_API_DEFAULT_ESTIMATE
        == (
            index_tail.LEGACY_ESTIMATE * index_tail.LEGACY_PER_PAGE
            + index_tail.DEFAULT_PER_PAGE
            - 1
        )
        // index_tail.DEFAULT_PER_PAGE
    )


def test_estimate_default_depends_on_url_and_custom_value_wins():
    member_url = "https://cafe.naver.com/ca-fe/cafes/29082876/members/KEY"
    html_url = "https://cafe.naver.com/ArticleList.nhn?search.clubid=29082876"

    assert index_tail._resolve_estimate(member_url, None) == 2121
    assert index_tail._resolve_estimate(html_url, None) == 2828
    assert index_tail._resolve_estimate(member_url, 77) == 77
    assert index_tail._resolve_estimate(html_url, 77) == 77


def test_cli_help_reports_url_specific_default_estimates(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["index_tail.py", "--help"])

    with pytest.raises(SystemExit) as excinfo:
        index_tail.main()

    assert excinfo.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "멤버 REST API 2121" in help_text
    assert "기존 HTML 2828" in help_text


def test_find_tail_forward_limit_fails_instead_of_returning_unconfirmed_page(monkeypatch):
    calls = []

    def always_has_rows(_session, _list_url, page_num, **_kwargs):
        calls.append(page_num)
        return ROWS, None

    monkeypatch.setattr(index_tail, "_fetch_rows_with_interactive_login", always_has_rows)
    monkeypatch.setattr(index_tail, "_sleep", lambda: None)

    assert index_tail.find_tail(FakeSession(), "https://example.test/list", 100) is None
    assert calls == list(range(100, 100 + index_tail.SCAN_FORWARD_MAX + 1))
