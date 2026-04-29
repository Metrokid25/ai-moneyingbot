"""src/collector.py — Phase 2 단건 본문 수집기 (retry logic 포함)."""
import sys
from pathlib import Path

# python src/collector.py 와 python -m src.collector 양쪽 지원
_src_dir = str(Path(__file__).parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import argparse
import os
import time
from typing import Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from browser import BrowserSession, check_blocked
from config import DEBUG_DIR
from db import (
    MAX_RETRY_ATTEMPTS,
    get_article_by_id,
    get_attempt_count,
    get_conn,
    record_attempt_start,
    record_body_collected,
    record_permanent_failure,
    record_transient_failure,
    reset_to_indexed,
)
from models import Status
from parser import parse_article

MIN_BODY_LENGTH = 50

CAFE_MAIN_FRAME_NAME = "cafe_main"
FRAME_MOUNT_TIMEOUT_S = 30
FRAME_POLL_INTERVAL_MS = 500
SELECTOR_TIMEOUT_MS = 10000

BODY_SELECTORS = [
    "div.article_viewer",
    "div.ContentRenderer",
    "div.article_container",
]

_VALID_SIMULATE = frozenset({"timeout", "navigation", "session", "empty"})


def _require_dev_mode(simulate_fail: str) -> None:
    if os.environ.get("DEV_MODE") != "1":
        raise SystemExit(
            f"[ERROR] --simulate-fail requires DEV_MODE=1 (simulate_fail={simulate_fail!r})"
        )


def _check_and_demote(conn, article_id: int, last_reason: str) -> None:
    count = get_attempt_count(conn, article_id)
    if count >= MAX_RETRY_ATTEMPTS:
        record_permanent_failure(
            conn,
            article_id,
            f"exceeded max retries (last: {last_reason}, attempts: {count})",
        )


def _handle_transient(conn, article_id: int, reason: str) -> None:
    record_transient_failure(conn, article_id, reason)
    conn.commit()
    _check_and_demote(conn, article_id, reason)
    conn.commit()


def collect_body(
    article_id: int,
    session: Optional[BrowserSession] = None,
    force: bool = False,
    simulate_fail: Optional[str] = None,
) -> str:
    """단건 본문 수집.

    Returns: 최종 status 값 (Status.BODY_* 상수 중 하나, 또는 Status.INDEXED)
    Raises: ValueError — article_id 가 DB 에 없을 때
            SystemExit — simulate_fail 사용 시 DEV_MODE=1 미설정
    """
    if simulate_fail is not None:
        _require_dev_mode(simulate_fail)
        if simulate_fail not in _VALID_SIMULATE:
            raise SystemExit(
                f"[ERROR] invalid simulate_fail={simulate_fail!r}, choices: {sorted(_VALID_SIMULATE)}"
            )

    article = get_article_by_id(article_id)
    if article is None:
        raise ValueError(f"article_id not found: {article_id}")

    conn = get_conn()
    try:
        # Fix #4: force는 INDEXED 포함 모든 비-완료 status에서 count 리셋
        if force and article.status != Status.BODY_COLLECTED:
            reset_to_indexed(conn, article_id, f"force recollect from {article.status}")
            conn.commit()
            article = get_article_by_id(article_id)

        if article.status != Status.INDEXED:
            print(f"[collector] skip {article_id}: status={article.status}")
            return article.status

        own_session = None
        if session is None:
            own_session = BrowserSession()
            session = own_session

        try:
            # Fix #3: 이전 실행이 중단돼 count만 쌓인 경우에도 pre-flight에서 강등
            pre_count = get_attempt_count(conn, article_id)
            if pre_count >= MAX_RETRY_ATTEMPTS:
                record_permanent_failure(
                    conn,
                    article_id,
                    f"exceeded max retries (accumulated attempts: {pre_count})",
                )
                conn.commit()
                print(f"[collector] DEMOTE pre-flight: count={pre_count} (article_id={article_id})")
                return Status.BODY_FAILED

            record_attempt_start(conn, article_id)
            conn.commit()

            matched_selector = None

            # ── navigation ────────────────────────────────────────────────
            final_url, err = session.goto(article.url)

            if simulate_fail == "navigation":
                raise Exception("simulated navigation interrupted")

            if err == "login_required":
                reason = "session expired (Phase2 전 임시 처리)"
                print(f"[collector] TRANSIENT: {reason} (article_id={article_id})")
                _handle_transient(conn, article_id, reason)
                return Status.INDEXED

            if err == "next_error":
                reason = "article deleted/not found"
                print(f"[collector] PERMANENT: {reason} (article_id={article_id})")
                _save_diagnostic(article_id, session)
                record_permanent_failure(conn, article_id, reason)
                conn.commit()
                return Status.BODY_FAILED

            if err in ("no_permission", "captcha", "age_verification"):
                reason = "session expired (Phase2 전 임시 처리)"
                print(f"[collector] TRANSIENT: err={err} (article_id={article_id})")
                _handle_transient(conn, article_id, reason)
                return Status.INDEXED

            if err is not None:
                reason = f"navigation: {err}"
                print(f"[collector] TRANSIENT: {reason} (article_id={article_id})")
                _handle_transient(conn, article_id, reason)
                return Status.INDEXED

            # Fix #1: timeout 주입을 frame mount 이전으로 이동 (실 세션 없이도 동작)
            if simulate_fail == "timeout":
                raise PlaywrightTimeoutError("simulated timeout: selector not found")

            # ── frame mount polling ───────────────────────────────────────
            deadline = time.monotonic() + FRAME_MOUNT_TIMEOUT_S
            frame = None
            while time.monotonic() < deadline:
                frame = session.page.frame(name=CAFE_MAIN_FRAME_NAME)
                if frame is None:
                    for fr in session.page.frames:
                        if fr.name == CAFE_MAIN_FRAME_NAME:
                            frame = fr
                            break
                if frame is not None:
                    break
                session.page.wait_for_timeout(FRAME_POLL_INTERVAL_MS)

            if frame is None:
                reason = f"timeout: cafe_main frame not found in {FRAME_MOUNT_TIMEOUT_S}s"
                print(f"[collector] TRANSIENT: {reason} (article_id={article_id})")
                _handle_transient(conn, article_id, reason)
                return Status.INDEXED

            # ── selector wait ─────────────────────────────────────────────
            for selector in BODY_SELECTORS:
                try:
                    frame.wait_for_selector(selector, timeout=SELECTOR_TIMEOUT_MS)
                    matched_selector = selector
                    break
                except PlaywrightTimeoutError:
                    continue
                except Exception:
                    continue

            if matched_selector is None:
                reason = f"timeout: no selector matched in {SELECTOR_TIMEOUT_MS // 1000}s"
                print(f"[collector] TRANSIENT: {reason} (article_id={article_id})")
                _handle_transient(conn, article_id, reason)
                return Status.INDEXED

            print(f"[collector] matched: {matched_selector} (article_id={article_id})")

            # ── empty body guard ──────────────────────────────────────────
            try:
                inner_html = frame.inner_html(matched_selector)
            except Exception:
                inner_html = ""

            if simulate_fail == "empty":
                inner_html = ""

            if not inner_html.strip():
                reason = f"empty body: {matched_selector}"
                print(f"[collector] TRANSIENT: {reason} (article_id={article_id})")
                _handle_transient(conn, article_id, reason)
                return Status.INDEXED

            # ── full frame HTML + block check ─────────────────────────────
            try:
                raw_html = frame.content()
            except Exception as e:
                reason = f"navigation: frame.content() failed: {e}"
                print(f"[collector] TRANSIENT: {reason} (article_id={article_id})")
                _handle_transient(conn, article_id, reason)
                return Status.INDEXED

            if simulate_fail == "session":
                block_reason = "login_required"
            else:
                block_reason = check_blocked(frame.url or "", raw_html)

            if block_reason == "login_required":
                reason = "session expired (Phase2 전 임시 처리)"
                print(f"[collector] TRANSIENT: {reason} (frame check, article_id={article_id})")
                _handle_transient(conn, article_id, reason)
                return Status.INDEXED
            elif block_reason:
                reason = "session expired (Phase2 전 임시 처리)"
                print(f"[collector] TRANSIENT: {reason} (article_id={article_id})")
                _handle_transient(conn, article_id, reason)
                return Status.INDEXED

            # ── parse ─────────────────────────────────────────────────────
            try:
                _title, _posted_at, clean_text, _raw_html_frag = parse_article(raw_html)
            except Exception as e:
                reason = f"parse error: {e}"
                print(f"[collector] PERMANENT: {reason} (article_id={article_id})")
                record_permanent_failure(conn, article_id, reason)
                conn.commit()
                return Status.BODY_FAILED

            if len(clean_text.strip()) < MIN_BODY_LENGTH:
                reason = f"empty body: {matched_selector}"
                print(f"[collector] TRANSIENT: short body (article_id={article_id})")
                _handle_transient(conn, article_id, reason)
                return Status.INDEXED

            record_body_collected(conn, article_id, raw_html, clean_text)
            conn.commit()
            print(f"[collector] BODY_COLLECTED (article_id={article_id})")
            return Status.BODY_COLLECTED

        except PlaywrightTimeoutError as e:
            sel_desc = matched_selector or BODY_SELECTORS[0]
            reason = f"timeout: {sel_desc} not found in {SELECTOR_TIMEOUT_MS // 1000}s"
            print(f"[collector] TRANSIENT: {reason} (article_id={article_id})")
            _handle_transient(conn, article_id, reason)
            return Status.INDEXED

        except SystemExit:
            raise

        except Exception as e:
            reason = f"navigation: {e}"
            print(f"[collector] TRANSIENT: {reason} (article_id={article_id})")
            _handle_transient(conn, article_id, reason)
            return Status.INDEXED

        finally:
            if own_session is not None:
                try:
                    own_session.close()
                except Exception as e:
                    print(f"[collector] session.close() error (ignored): {e}")

    finally:
        conn.close()


def _save_diagnostic(article_id: int, session: BrowserSession) -> None:
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        html = session.page.content()
        url = session.page.url
        (DEBUG_DIR / f"diagnostic_next_error_{article_id}.html").write_text(html, encoding="utf-8")
        (DEBUG_DIR / f"diagnostic_next_error_{article_id}.url.txt").write_text(url, encoding="utf-8")
    except Exception as e:
        print(f"[collector] diagnostic save failed: {e}")


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="단건 본문 수집")
    p.add_argument("--article-id", type=int, required=True)
    p.add_argument("--force", action="store_true", help="BODY_FAILED/BLOCKED도 재수집")
    p.add_argument(
        "--simulate-fail",
        choices=sorted(_VALID_SIMULATE),
        default=None,
        help="실패 주입 (DEV_MODE=1 필수)",
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.path.insert(0, "src")
    args = _parse_args()
    result = collect_body(
        article_id=args.article_id,
        force=args.force,
        simulate_fail=args.simulate_fail,
    )
    print(f"[result] article_id={args.article_id} → {result}")
    sys.exit(0 if result == Status.BODY_COLLECTED else 1)
