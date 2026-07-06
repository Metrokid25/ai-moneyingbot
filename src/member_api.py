"""멤버 작성글 목록 API 클라이언트.

2026-07-02: 네이버가 멤버 작성글 목록 페이지(/f-e/, /ca-fe/)를 클라이언트 렌더
SPA로 바꿔 HTML 파싱(parse_article_list)이 0행이 됨. SPA가 실제로 쓰는 REST API
(cafe-web/cafe-mobile/CafeMemberNetworkArticleListV3)를 직접 호출한다.
엔드포인트/파라미터는 ca-fe.pstatic.net web-section 번들(app.f4cd1f6c.js)의
getMemberArticles 구현에서 확인함.

로그인 감지: 이 API는 비로그인 시 code 0004("로그인하지 않았습니다")를 반환한다.
빈 SPA 셸 HTML 휴리스틱보다 신뢰할 수 있는 로그인 판별 신호다.
"""
import datetime
import re
from typing import Optional, Tuple

MEMBER_ARTICLES_API = (
    "https://apis.naver.com/cafe-web/cafe-mobile/CafeMemberNetworkArticleListV3"
)
NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login?url=https%3A%2F%2Fcafe.naver.com"
DEFAULT_PER_PAGE = 20

# /f-e/cafes/<cafeId>/members/<memberKey> 또는 /ca-fe/cafes/... 형태
_MEMBER_URL_RE = re.compile(r"/cafes/(\d+)/members/([A-Za-z0-9_\-]+)")


def parse_member_list_url(list_url: str) -> Optional[Tuple[str, str]]:
    """멤버 작성글 목록 URL에서 (cafe_id, member_key) 추출. 아니면 None."""
    m = _MEMBER_URL_RE.search(list_url)
    if not m:
        return None
    return m.group(1), m.group(2)


# 사람 개입이 필요한 '차단'(로그인/캡차/권한/본인인증). 이것만 상주 루프를 멈춰야 하고,
# 네트워크/타임아웃/일시 API 오류는 다음 주기 재시도 대상(루프를 죽이면 안 됨).
_BLOCK_ERROR_MARKERS = ("login_required", "captcha", "no_permission", "age_verification")


def is_block_error(err) -> bool:
    """err이 사람 개입 필요한 차단이면 True. 일시적 네트워크/API 오류면 False."""
    if not err:
        return False
    return any(marker in str(err) for marker in _BLOCK_ERROR_MARKERS)


def _clean_error(exc) -> str:
    """Playwright 예외 문자열의 'Call log:' 이하(요청 헤더·세션 쿠키 포함)를 잘라낸다.

    APIRequestContext 예외 str에는 요청 로그가 붙고 거기 cookie 헤더(NID_AUT/NID_SES 등)가
    평문으로 들어있다 → 로그/에러 문자열에 세션 쿠키가 새지 않도록 첫 줄만 남긴다."""
    msg = str(exc).split("Call log:")[0].strip()
    return msg or type(exc).__name__


def _format_posted_at(item: dict) -> Optional[str]:
    ts = item.get("writeDateTimestamp") or item.get("writedt")
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            return datetime.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            pass
    write_date = item.get("writeDate")
    if isinstance(write_date, str) and write_date:
        return write_date
    return None


def fetch_member_articles(
    session,
    cafe_id: str,
    member_key: str,
    page: int,
    *,
    per_page: int = DEFAULT_PER_PAGE,
    timeout_ms: int = 15000,
):
    """(rows_or_None, err_or_None) 반환. rows는 parse_article_list와 동일 스키마.

    session은 BrowserSession — persistent context의 쿠키를 그대로 실어 보내기 위해
    context 레벨 request를 사용한다 (브라우저에서 로그인하면 즉시 반영됨).
    """
    try:
        resp = session._context.request.get(
            MEMBER_ARTICLES_API,
            params={
                "search.cafeId": cafe_id,
                "search.memberKey": member_key,
                "search.perPage": per_page,
                "search.page": page,
                "requestFrom": "A",
            },
            headers={
                "referer": f"https://cafe.naver.com/ca-fe/cafes/{cafe_id}/members/{member_key}",
                "accept": "application/json",
            },
            timeout=timeout_ms,
        )
    except Exception as e:  # 네트워크/타임아웃
        return None, f"member_api_request_failed: {_clean_error(e)}"

    if resp.status in (401, 403):
        # 게이트웨이 레벨 인증 거부 — 대화형 로그인 재시도가 발동하도록 login_required로 분류
        return None, f"login_required: member_api_http_{resp.status}"
    if resp.status != 200:
        return None, f"member_api_http_{resp.status}"

    try:
        data = resp.json()
    except Exception as e:
        return None, f"member_api_bad_json: {_clean_error(e)}"

    message = data.get("message") or {}
    error = message.get("error") or {}
    # 주의: 성공 응답에도 빈 error 객체({"code":"","msg":""})가 포함될 수 있다.
    # error 키 존재가 아니라 code/msg 내용으로 에러를 판별한다.
    code = (error.get("code") or "").strip() if isinstance(error, dict) else ""
    msg = (error.get("msg") or "").strip() if isinstance(error, dict) else str(error)
    if code or msg:
        if code == "0004" or "로그인" in msg:
            return None, f"login_required: member_api code={code} ({msg})"
        return None, f"member_api_error code={code} ({msg})"

    result = message.get("result") or {}
    if not result and str(message.get("status", "")) not in ("200", ""):
        # 에러도 결과도 없는 비정상 응답 — 원문 일부를 남겨 진단 가능하게
        return None, f"member_api_unexpected status={message.get('status')} body={str(data)[:200]}"
    article_list = result.get("articleList") or []

    rows = []
    for item in article_list:
        article_id = item.get("articleId") or item.get("articleid")
        if not isinstance(article_id, int):
            continue
        rows.append({
            "article_id": article_id,
            "title": (item.get("subject") or "").strip(),
            # 기존 목록 파서와 동일한 URL 형태 유지 → 본문수집(batch_recollect) 호환
            "url": f"https://cafe.naver.com/ArticleRead.nhn?clubid={cafe_id}&articleid={article_id}",
            "posted_at": _format_posted_at(item),
        })

    # 데이터는 왔는데 한 건도 파싱 못 함 = 응답 스키마 변경 의심 —
    # '진짜 빈 페이지'와 구분되는 에러로 알려 조용한 0건 수집을 막는다.
    if article_list and not rows:
        return None, f"member_api_schema_mismatch: 0/{len(article_list)} rows parseable"
    return rows, None


def check_member_login(session, cafe_id: str, member_key: str):
    """로그인 상태 프로브. (True|False|None, detail) 반환.

    True=로그인됨, False=로그아웃 확정(0004 등), None=판별 불가(프로브 실패 —
    테스트용 가짜 세션이나 네트워크 오류 등. 호출부는 기존 동작으로 폴백할 것).
    """
    try:
        rows, err = fetch_member_articles(session, cafe_id, member_key, 1)
    except Exception as e:
        return None, f"probe_failed: {_clean_error(e)}"
    if err is None:
        return True, f"ok ({len(rows)} rows)"
    if err.startswith("login_required"):
        return False, err
    return None, err
