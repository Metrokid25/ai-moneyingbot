"""src/collector.py — Phase 2 단건 본문 수집기.

설계 문서: docs/phase2_design.md 섹션 4
"""
from typing import Optional

from browser import BrowserSession, check_blocked
from config import DEBUG_DIR
from db import get_article_by_id, update_article_body
from models import Status
from parser import parse_article


MIN_BODY_LENGTH = 50

CAFE_MAIN_FRAME_NAME = "cafe_main"
SELECTOR_TIMEOUT_MS = 10000

BODY_SELECTORS = [
    "div.article_viewer",       # 1순위: 순수 본문
    "div.ContentRenderer",      # 2순위: 동등 후보
    "div.article_container",    # 3순위: 본문+메타 (fallback)
]


def collect_body(
    article_id: int,
    session: Optional[BrowserSession] = None,
) -> str:
    """단건 본문 수집. 호출자가 session 주입 시 재사용, None 이면 내부 생성.

    Returns: 최종 status 값 (Status.BODY_* 상수 중 하나)
    Raises: ValueError — article_id 가 DB 에 없을 때
    """
    article = get_article_by_id(article_id)
    if article is None:
        raise ValueError(f"article_id not found: {article_id}")

    if article.status in (Status.BODY_COLLECTED, Status.BODY_BLOCKED):
        print(f"[collector] skip {article_id}: already {article.status}")
        return article.status

    own_session = None
    if session is None:
        own_session = BrowserSession()
        session = own_session

    try:
        final_url, err = session.goto(article.url)

        if err == "login_required":
            print(f"[collector] BLOCKED: err=login_required (article_id={article_id})")
            update_article_body(article_id, "", "", Status.BODY_BLOCKED, error_reason=err)
            return Status.BODY_BLOCKED

        if err == "next_error":
            print(f"[collector] FAILED: err=next_error (article_id={article_id})")
            _save_diagnostic(article_id, session)
            update_article_body(article_id, "", "", Status.BODY_FAILED, error_reason=err)
            return Status.BODY_FAILED

        if err in ("no_permission", "captcha", "age_verification"):
            print(f"[collector] BLOCKED: err={err} (article_id={article_id})")
            update_article_body(article_id, "", "", Status.BODY_BLOCKED, error_reason=err)
            return Status.BODY_BLOCKED

        if err is not None and err.startswith("navigation_failed"):
            print(f"[collector] FAILED: err={err} (article_id={article_id})")
            update_article_body(article_id, "", "", Status.BODY_FAILED, error_reason=err)
            return Status.BODY_FAILED

        if err is not None:
            print(f"[collector] FAILED: unknown err={err} (article_id={article_id})")
            update_article_body(article_id, "", "", Status.BODY_FAILED, error_reason=err)
            return Status.BODY_FAILED

        session.page.wait_for_timeout(2000)

        frame = session.page.frame(name=CAFE_MAIN_FRAME_NAME)
        if frame is None:
            for fr in session.page.frames:
                if fr.name == CAFE_MAIN_FRAME_NAME:
                    frame = fr
                    break
        if frame is None:
            print(f"[collector] FAILED: cafe_main frame not found (article_id={article_id})")
            try:
                page_html = session.page.content()
            except Exception:
                page_html = ""
            update_article_body(article_id, page_html, "", Status.BODY_FAILED,
                                error_reason="cafe_main_frame_not_found")
            return Status.BODY_FAILED

        raw_html = frame.content()
        block_reason = check_blocked(frame.url or "", raw_html)
        if block_reason:
            print(f"[collector] BLOCKED in frame: {block_reason} (article_id={article_id})")
            update_article_body(article_id, raw_html, "", Status.BODY_BLOCKED,
                                error_reason=block_reason)
            return Status.BODY_BLOCKED

        matched_selector = None
        for selector in BODY_SELECTORS:
            try:
                frame.wait_for_selector(selector, timeout=SELECTOR_TIMEOUT_MS)
                matched_selector = selector
                break
            except Exception:
                continue

        if matched_selector is None:
            print(f"[collector] FAILED: no selector matched in cafe_main frame (article_id={article_id})")
            update_article_body(article_id, raw_html, "", Status.BODY_FAILED,
                                error_reason="selector_timeout")
            return Status.BODY_FAILED

        print(f"[collector] matched: {matched_selector} (article_id={article_id})")

        html = raw_html

        try:
            _title, _posted_at, clean_text, _raw_html_frag = parse_article(html)
        except Exception as e:
            print(f"[collector] parse_article failed: {e}")
            update_article_body(article_id, html, "", Status.BODY_FAILED,
                                error_reason="parse_failed")
            return Status.BODY_FAILED

        if len(clean_text.strip()) < MIN_BODY_LENGTH:
            update_article_body(article_id, html, clean_text, Status.BODY_EMPTY)
            return Status.BODY_EMPTY

        update_article_body(article_id, html, clean_text, Status.BODY_COLLECTED)
        return Status.BODY_COLLECTED

    finally:
        if own_session is not None:
            own_session.close()


def _save_diagnostic(article_id: int, session: BrowserSession) -> None:
    """next_error 발생 시 진단 HTML 보존. indexer.py 진단 저장 패턴과 동일."""
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        html = session.page.content()
        url = session.page.url
        html_path = DEBUG_DIR / f"diagnostic_next_error_{article_id}.html"
        url_path = DEBUG_DIR / f"diagnostic_next_error_{article_id}.url.txt"
        html_path.write_text(html, encoding="utf-8")
        url_path.write_text(url, encoding="utf-8")
        print(f"[collector] diagnostic → {html_path}")
    except Exception as e:
        print(f"[collector] diagnostic save failed: {e}")
