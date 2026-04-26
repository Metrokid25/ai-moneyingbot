from typing import Optional, Tuple
from playwright.sync_api import (
    sync_playwright, Page, Browser, BrowserContext,
    Error as PlaywrightError,
)
from config import BROWSER_TIMEOUT_MS, HEADLESS

_BLOCK_URL: list[Tuple[str, str]] = [
    ("login_required", "nid.naver.com"),
]

_BLOCK_CONTENT: list[Tuple[str, str]] = [
    ("login_required",   "로그인이 필요"),
    ("login_required",   "로그인 후 이용"),
    ("no_permission",    "접근 권한이 없습니다"),
    ("no_permission",    "가입한 회원만"),
    ("no_permission",    "이 카페는 가입 후"),
    ("no_permission",    "비공개 카페"),
    ("captcha",          "자동입력 방지문자"),
    ("age_verification", "본인확인"),
    ("age_verification", "성인인증"),
]


def _is_login_page(page: Page) -> bool:
    """현재 페이지가 로그인 페이지인지 감지."""
    url = page.url
    if "nid.naver.com" in url:
        print("[DEBUG] 로그인 페이지 감지: nid.naver.com URL")
        return True
    if "login" in url:
        print("[DEBUG] 로그인 페이지 감지: login URL")
        return True

    try:
        html = page.content()
    except PlaywrightError:
        html = ""

    if "NotLoggedInError" in html:
        print("[DEBUG] 로그인 페이지 감지: NotLoggedInError 문자열 존재")
        return True
    if "카페 멤버이시면 먼저 로그인을 해야 합니다" in html:
        print("[DEBUG] 로그인 페이지 감지: 로그인 안내 문자열 존재")
        return True
    if 'id="__next_error__"' in html:
        print("[DEBUG] 로그인 페이지 감지: __next_error__ 태그 존재")
        return True

    try:
        if page.query_selector('input[id="id"], input[name="id"]'):
            print("[DEBUG] 로그인 페이지 감지: id 입력 필드 존재")
            return True
    except PlaywrightError:
        pass

    return False


def wait_for_login(page: Page) -> None:
    """로그인 페이지면 사용자가 엔터를 칠 때까지 무한 대기.

    이미 로그인된 세션이면 즉시 반환.
    """
    if not _is_login_page(page):
        return
    input("[LOGIN] 브라우저에서 로그인을 완료한 뒤, 이 콘솔에서 엔터를 눌러주세요.")
    print("[LOGIN] 진행합니다")


def check_blocked(url: str, content: str) -> Optional[str]:
    for reason, signal in _BLOCK_URL:
        if signal in url:
            return reason
    for reason, signal in _BLOCK_CONTENT:
        if signal in content:
            return reason
    return None


class BrowserSession:
    """단일 브라우저 세션. indexer에서 페이지 간 재사용."""

    def __init__(self) -> None:
        self._pw = sync_playwright().start()
        self._browser: Browser = self._pw.chromium.launch(headless=HEADLESS)
        self._context: BrowserContext = self._browser.new_context()
        self._page: Page = self._context.new_page()

    @property
    def page(self) -> Page:
        return self._page

    def goto(self, url: str) -> Tuple[str, Optional[str]]:
        """URL로 이동. (final_url, error_reason) 반환."""
        try:
            self._page.goto(url, timeout=BROWSER_TIMEOUT_MS, wait_until="domcontentloaded")
        except PlaywrightError as e:
            return url, f"navigation_failed: {e}"

        final_url = self._page.url
        blocked = check_blocked(final_url, self._page.content())
        if blocked:
            return final_url, blocked
        return final_url, None

    def get_frame_html(self) -> Tuple[Optional[str], Optional[str]]:
        """cafe_main iframe HTML 반환. (html, error_reason)"""
        try:
            frame = self._page.frame(name="cafe_main")
            if frame is not None:
                frame.wait_for_load_state("domcontentloaded", timeout=BROWSER_TIMEOUT_MS)
                html = frame.content()
                blocked = check_blocked(frame.url or "", html)
                if blocked:
                    return None, blocked
                return html, None
            return self._page.content(), None
        except PlaywrightError as e:
            return None, f"frame_load_failed: {e}"

    def screenshot(self, path: str) -> None:
        try:
            self._page.screenshot(path=path, full_page=True)
        except PlaywrightError:
            pass

    def close(self) -> None:
        self._browser.close()
        self._pw.stop()


def fetch_page(url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """단일 글 수집용 one-shot fetch. (final_url, html, error_reason)"""
    session = BrowserSession()
    try:
        final_url, err = session.goto(url)
        if err:
            return final_url, None, err
        html, err = session.get_frame_html()
        return final_url, html, err
    finally:
        session.close()
