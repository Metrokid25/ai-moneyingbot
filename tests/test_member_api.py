import sys

sys.path.insert(0, "src")

import member_api
from member_api import fetch_member_articles, parse_member_list_url


def test_parse_member_list_url_fe_and_cafe_variants():
    key = "THEA7uBzD6uKXKno57_Bl7jItzRnvmuDMltnPsGI9BY"
    for prefix in ("f-e", "ca-fe"):
        url = f"https://cafe.naver.com/{prefix}/cafes/29082876/members/{key}?page=3"
        assert parse_member_list_url(url) == ("29082876", key)


def test_parse_member_list_url_rejects_non_member_urls():
    assert parse_member_list_url("https://cafe.naver.com/list?page=1") is None
    assert parse_member_list_url("https://cafe.naver.com/ArticleList.nhn?search.clubid=1") is None


def test_is_block_error_only_true_for_human_intervention_cases():
    assert member_api.is_block_error("login_required: member_api code=0004") is True
    assert member_api.is_block_error("no_permission") is True
    assert member_api.is_block_error("captcha") is True
    assert member_api.is_block_error("age_verification") is True
    # 일시적 네트워크/API 오류는 차단이 아님 → 상주 루프를 멈추면 안 됨
    assert member_api.is_block_error("member_api_request_failed: socket hang up") is False
    assert member_api.is_block_error("member_api_http_503") is False
    assert member_api.is_block_error("member_api_bad_json: x") is False
    assert member_api.is_block_error(None) is False
    assert member_api.is_block_error("") is False


def test_clean_error_strips_call_log_and_session_cookies():
    exc = Exception(
        "APIRequestContext.get: socket hang up\n"
        "Call log:\n  - -> GET https://apis.naver.com/cafe-web/...\n"
        "  - cookie: NID_AUT=SECRET_AUTH_VALUE; NID_SES=SECRET_SES_VALUE"
    )
    cleaned = member_api._clean_error(exc)
    assert cleaned == "APIRequestContext.get: socket hang up"
    assert "NID_AUT" not in cleaned and "SECRET" not in cleaned and "cookie" not in cleaned


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    def json(self):
        return self._payload


class _FakeRequest:
    def __init__(self, payload, status=200):
        self._payload = payload
        self._status = status
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params))
        return _FakeResponse(self._payload, self._status)


class _FakeContext:
    def __init__(self, request):
        self.request = request


class _FakeSession:
    def __init__(self, payload, status=200):
        self._context = _FakeContext(_FakeRequest(payload, status))


def test_fetch_member_articles_maps_rows():
    payload = {
        "message": {
            "status": "200",
            "result": {
                "articleList": [
                    {
                        "articleId": 172396,
                        "subject": "  제목입니다  ",
                        "writeDateTimestamp": 1751264568000,
                    },
                    {"articleid": 172395, "subject": "소문자 필드"},
                    {"subject": "id 없음 → 스킵"},
                ],
            },
        }
    }
    session = _FakeSession(payload)
    rows, err = fetch_member_articles(session, "29082876", "KEY", 1)

    assert err is None
    assert [r["article_id"] for r in rows] == [172396, 172395]
    assert rows[0]["title"] == "제목입니다"
    assert rows[0]["url"] == (
        "https://cafe.naver.com/ArticleRead.nhn?clubid=29082876&articleid=172396"
    )
    assert rows[0]["posted_at"] is not None
    # 요청 파라미터 계약 확인
    _url, params = session._context.request.calls[0]
    assert params["search.cafeId"] == "29082876"
    assert params["search.page"] == 1


def test_fetch_member_articles_detects_login_required():
    payload = {
        "message": {
            "status": "500",
            "error": {"code": "0004", "msg": "로그인하지 않았습니다"},
        }
    }
    rows, err = fetch_member_articles(_FakeSession(payload), "1", "KEY", 1)
    assert rows is None
    assert err is not None and "login_required" in err


def test_fetch_member_articles_reports_other_api_errors():
    payload = {
        "message": {
            "status": "500",
            "error": {"code": "9999", "msg": "오류"},
        }
    }
    rows, err = fetch_member_articles(_FakeSession(payload), "1", "KEY", 1)
    assert rows is None
    assert err is not None and "member_api_error" in err and "login_required" not in err


def test_fetch_member_articles_http_error():
    rows, err = fetch_member_articles(_FakeSession({}, status=503), "1", "KEY", 1)
    assert rows is None
    assert err == "member_api_http_503"


def test_fetch_member_articles_empty_list_is_empty_rows_not_error():
    payload = {"message": {"status": "200", "result": {"articleList": []}}}
    rows, err = fetch_member_articles(_FakeSession(payload), "1", "KEY", 1)
    assert err is None
    assert rows == []


def test_fetch_member_articles_401_403_map_to_login_required():
    for status in (401, 403):
        rows, err = fetch_member_articles(_FakeSession({}, status=status), "1", "KEY", 1)
        assert rows is None
        assert err == f"login_required: member_api_http_{status}"


def test_fetch_member_articles_schema_mismatch_is_error_not_empty():
    # articleList에 데이터가 있는데 한 건도 파싱 못 하면 '빈 페이지'가 아니라 에러여야 한다
    payload = {
        "message": {
            "status": "200",
            "result": {"articleList": [{"articleId": "172396", "subject": "문자열 id"}]},
        }
    }
    rows, err = fetch_member_articles(_FakeSession(payload), "1", "KEY", 1)
    assert rows is None
    assert err is not None and "member_api_schema_mismatch" in err


def test_check_member_login_states():
    from member_api import check_member_login

    ok_payload = {"message": {"status": "200", "result": {"articleList": [{"articleId": 1, "subject": "t"}]}}}
    logged_in, _ = check_member_login(_FakeSession(ok_payload), "1", "KEY")
    assert logged_in is True

    out_payload = {"message": {"status": "500", "error": {"code": "0004", "msg": "로그인하지 않았습니다"}}}
    logged_in, detail = check_member_login(_FakeSession(out_payload), "1", "KEY")
    assert logged_in is False and "login_required" in detail

    # 프로브 불가(가짜 세션에 _context 없음) → None
    class _Bare:
        pass

    logged_in, _ = check_member_login(_Bare(), "1", "KEY")
    assert logged_in is None


def test_fetch_member_articles_ignores_empty_error_object_on_success():
    # 네이버 API는 성공 응답에도 빈 error 객체를 포함할 수 있다 — 에러로 오판하면 안 됨
    payload = {
        "message": {
            "status": "200",
            "error": {"code": "", "msg": ""},
            "result": {"articleList": [{"articleId": 172397, "subject": "새 글"}]},
        }
    }
    rows, err = fetch_member_articles(_FakeSession(payload), "29082876", "KEY", 1)
    assert err is None
    assert [r["article_id"] for r in rows] == [172397]
