"""Reusable list indexing bridge based on the proven index_tail flow."""
from __future__ import annotations

import time
from typing import Any, Callable

from browser import (
    BrowserSession,
    check_blocked,
    detect_login_state,
    format_login_detection_summary,
    has_article_list_marker,
)
from indexer import build_page_url
from member_api import fetch_member_articles, parse_member_list_url
from parser import parse_article_list

LIST_PAGE_READY_RETRIES = 3
LIST_PAGE_READY_DELAY_SECONDS = 1.0


def fetch_index_rows(
    session: BrowserSession,
    list_url: str,
    page_num: int,
    *,
    ready_retries: int = LIST_PAGE_READY_RETRIES,
    ready_delay_seconds: float = LIST_PAGE_READY_DELAY_SECONDS,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Fetch one list page using the same primitives as scripts/index_tail.py."""
    # 2026-07-02: 멤버 작성글 목록은 SPA로 바뀌어 HTML 파싱이 0행 → REST API 사용.
    member = parse_member_list_url(list_url)
    if member is not None:
        cafe_id, member_key = member
        rows, err = fetch_member_articles(session, cafe_id, member_key, page_num)
        if err:
            # 이 레이어의 기존 계약은 정확히 "login_required" 문자열 비교
            if err.startswith("login_required"):
                return None, "login_required"
            return None, err
        for row in rows:
            row.setdefault("source_page", page_num)
        return rows, None

    page_url = build_page_url(list_url, page_num)
    final_url, err = session.goto(page_url)
    if err and err != "login_required":
        return None, err

    last_error = err
    last_detection = None
    current_url = _safe_current_url(session, final_url)
    title = _safe_page_title(session)
    for attempt in range(1, max(1, ready_retries) + 1):
        html, frame_err = session.get_frame_html()
        current_url = _safe_current_url(session, final_url)
        title = _safe_page_title(session)

        if frame_err and frame_err != "login_required":
            return None, frame_err

        if html is None:
            last_error = frame_err or "frame_load_failed"
            page_html = _safe_page_content(session)
            if page_html:
                last_detection = detect_login_state(current_url, page_html)
                if _is_definite_login_required(last_detection):
                    _print_login_required_diagnostics(current_url, title, last_detection)
                    return None, "login_required"
        else:
            last_detection = detect_login_state(current_url, html)
            if has_article_list_marker(html):
                return _parse_rows_with_source_page(html, current_url, page_num), None

            blocked = check_blocked(current_url, html)
            if blocked and _is_definite_login_required(last_detection):
                _print_login_required_diagnostics(current_url, title, last_detection)
                return None, blocked
            if blocked:
                last_error = blocked
            else:
                rows = _parse_rows_with_source_page(html, current_url, page_num)
                if rows:
                    return rows, None
                # frame_err는 이 분기에서 항상 None → 앞선 시도가 기록한 의미 있는
                # 사유(goto의 login_required 등)를 None으로 덮어쓰지 않는다. 덮어쓰면
                # ([], None)으로 반환돼 차단이 '빈 페이지 성공'으로 위장된다(조용한 0건).
                last_error = frame_err or last_error

        if attempt < max(1, ready_retries):
            sleeper(ready_delay_seconds)

    if last_detection is not None and last_error == "login_required":
        _print_login_required_diagnostics(current_url, title, last_detection)
    if last_error is None:
        return [], None
    return None, last_error


def collect_index_rows(
    session: BrowserSession,
    list_url: str,
    *,
    limit: int,
    page_limit: int,
    delay_seconds: float,
    sleeper: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Collect bounded list rows through the proven index_tail-style fetch path."""
    rows: list[dict[str, Any]] = []
    for page_num in range(1, page_limit + 1):
        page_rows, err = fetch_index_rows(session, list_url, page_num, sleeper=sleeper)
        if err:
            raise RuntimeError(f"list page {page_num} failed: {err}")

        for row in page_rows or []:
            rows.append(row)
            if len(rows) >= limit:
                return rows

        if page_num < page_limit:
            sleeper(delay_seconds)

    return rows


def _parse_rows_with_source_page(html: str, url: str, page_num: int) -> list[dict[str, Any]]:
    rows = parse_article_list(html, url)
    for row in rows:
        row.setdefault("source_page", page_num)
    return rows


def _safe_page_title(session: Any) -> str:
    page = getattr(session, "page", None)
    title = getattr(page, "title", None)
    if not callable(title):
        return "-"
    try:
        return str(title())
    except Exception:
        return "-"


def _safe_current_url(session: Any, fallback: str) -> str:
    page = getattr(session, "page", None)
    return str(getattr(page, "url", None) or fallback)


def _safe_page_content(session: Any) -> str:
    page = getattr(session, "page", None)
    content = getattr(page, "content", None)
    if not callable(content):
        return ""
    try:
        return str(content())
    except Exception:
        return ""


def _is_definite_login_required(detection: Any) -> bool:
    return bool(
        detection
        and detection.reason == "login_required"
        and (
            detection.current_url_is_login
            or detection.password_input_found
            or detection.detail == "login form detected"
            or detection.detail == "redirected to login url"
            or detection.detail == "redirected to login path"
        )
    )


def _print_login_required_diagnostics(url: str, title: str, detection: Any) -> None:
    print(
        "[DEBUG] login_required detected: "
        f"{detection.detail}; url={url}; title={title}; "
        f"{format_login_detection_summary(detection)}"
    )
