import sys
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse
from playwright.sync_api import (
    sync_playwright, Page, Browser, BrowserContext,
    Error as PlaywrightError,
)
from config import BROWSER_TIMEOUT_MS, DEFAULT_BROWSER_PROFILE_DIR, HEADLESS

_BLOCK_URL: list[Tuple[str, str]] = [
    ("login_required", "nid.naver.com"),
]

_BLOCK_CONTENT: list[Tuple[str, str]] = [
    ("login_required",   "로그인이 필요"),
    ("login_required",   "로그인 후 이용"),
    ("no_permission",    "접근 권한이 없습니다"),
    ("no_permission",    "가입한 회원만 이용"),
    ("no_permission",    "이 카페는 가입 후"),
    ("no_permission",    "비공개 카페로 회원만"),
    ("captcha",          "자동입력 방지문자"),
    # ("age_verification", "본인확인"),  # 2026-04-27: genderUnknownLayer 모달이 모든 페이지 DOM에 박혀있어 false positive
    # ("age_verification", "성인인증"),  # 2026-04-27: 119investment 카페는 성인인증 대상 아님 (멤버 수년 경험상 0건)
]


_ARTICLE_LIST_MARKERS = (
    "article-board",
    "board-box",
    "article_list",
    "board_list_w",
    "board-list__item",
    "td_article",
    "articleid=",
    "articleid%3d",
)

_LOGIN_FORM_MARKERS = (
    'id="id"',
    "id='id'",
    'name="id"',
    "name='id'",
    'id="pw"',
    "id='pw'",
    'name="pw"',
    "name='pw'",
    'type="password"',
    "type='password'",
    "nidlogin.login",
)

_LOGIN_REQUIRED_MARKERS = (
    "notloggedinerror",
    "login_required",
    "로그인이 필요",
    "로그인 후 이용",
    "먼저 로그인",
)


def _has_article_list_marker(html: str) -> bool:
    lowered = html.lower()
    return any(marker in lowered for marker in _ARTICLE_LIST_MARKERS)


def _has_login_marker(html: str) -> bool:
    lowered = html.lower()
    return any(marker in lowered for marker in _LOGIN_FORM_MARKERS) or any(
        marker.lower() in lowered for marker in _LOGIN_REQUIRED_MARKERS
    )


def detect_login_required(
    url: str,
    html: str,
    *,
    login_form_visible: bool = False,
) -> tuple[Optional[str], Optional[str]]:
    """Return login_required only when the page is actually a login/block page."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "nid.naver.com" in host:
        return "login_required", "redirected to login url"
    if "login" in path and ("naver.com" in host or not host):
        return "login_required", "redirected to login path"
    if login_form_visible:
        return "login_required", "login form detected"

    has_article_list = _has_article_list_marker(html)
    has_login_marker = _has_login_marker(html)
    if has_article_list:
        return None, "article-list markers found"
    if has_login_marker:
        return "login_required", "no article-list markers found and login marker visible"
    return None, None


def _legacy_is_login_page(page: Page) -> Optional[str]:
    """현재 페이지 상태 감지. 'login_required', 'next_error', None 중 하나 반환."""
    url = page.url
    if "nid.naver.com" in url:
        print("[DEBUG] 로그인 페이지 감지: nid.naver.com URL")
        return "login_required"
    if "login" in url:
        print("[DEBUG] 로그인 페이지 감지: login URL")
        return "login_required"

    try:
        html = page.content()
    except PlaywrightError:
        html = ""

    if False and "legacy_disabled_not_logged_in_error" in html:
        print("[DEBUG] legacy login detector disabled")
        return "login_required"
    if "카페 멤버이시면 먼저 로그인을 해야 합니다" in html:
        print("[DEBUG] 로그인 페이지 감지: 로그인 안내 문자열 존재")
        return "login_required"
    if 'id="__next_error__"' in html:
        # auth 마커 없이 __next_error__ 단독 → Next.js 일반 에러, 진단 저장 필요
        print("[DEBUG] next_error 감지: __next_error__ 존재 (auth 마커 없음)")
        return "next_error"

    try:
        if page.query_selector('input[id="id"], input[name="id"]'):
            print("[DEBUG] 로그인 페이지 감지: id 입력 필드 존재")
            return "login_required"
    except PlaywrightError:
        pass

    return None


def _is_login_page(page: Page) -> Optional[str]:
    """Detect login pages without treating embedded error strings as decisive."""
    url = page.url
    try:
        title = page.title()
    except PlaywrightError:
        title = "-"
    try:
        html = page.content()
    except PlaywrightError:
        html = ""

    login_form_visible = False
    try:
        if page.query_selector('input[id="id"], input[name="id"], input[type="password"]'):
            login_form_visible = True
    except PlaywrightError:
        pass

    reason, detail = detect_login_required(url, html, login_form_visible=login_form_visible)
    if reason:
        print(f"[DEBUG] login_required detected: {detail}; url={url}; title={title}")
        return reason
    if detail == "article-list markers found":
        print("[DEBUG] login_required skipped: article-list markers found")
    if 'id="__next_error__"' in html:
        print("[DEBUG] next_error detected: __next_error__ without login markers")
        return "next_error"
    return None


def wait_for_login(page: Page) -> None:
    """로그인 페이지면 사용자가 엔터를 칠 때까지 무한 대기.

    이미 로그인된 세션이면 즉시 반환.
    Windows PowerShell에서 input()이 stdin EOF를 받아 즉시 통과하는 문제를
    msvcrt.getwch()로 콘솔 직접 읽기(CONIN$)로 우회.
    """
    if _is_login_page(page) != "login_required":
        return
    print("[LOGIN] 브라우저에서 로그인을 완료한 뒤, 이 콘솔에서 엔터를 눌러주세요.", flush=True)
    if sys.platform == "win32":
        import msvcrt
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                break
    else:
        sys.stdin.readline()
    print("[LOGIN] 진행합니다")
    print("[LOGIN] 세션 안정화를 위해 3초 대기")
    time.sleep(3)


def check_blocked(url: str, content: str) -> Optional[str]:
    login_reason, _detail = detect_login_required(url, content)
    if login_reason:
        return login_reason
    for reason, signal in _BLOCK_URL:
        if signal in url:
            return reason
    for reason, signal in _BLOCK_CONTENT:
        if signal in content:
            return reason
    return None


class BrowserSession:
    """단일 브라우저 세션. indexer에서 페이지 간 재사용."""

    def __init__(
        self,
        *,
        user_data_dir: str | Path | None = None,
        persistent: bool = True,
        headless: bool | None = None,
    ) -> None:
        self._pw = sync_playwright().start()
        self._browser: Browser | None = None
        self.user_data_dir = Path(user_data_dir or DEFAULT_BROWSER_PROFILE_DIR)
        browser_headless = HEADLESS if headless is None else headless
        if persistent:
            self.user_data_dir.mkdir(parents=True, exist_ok=True)
            self._context: BrowserContext = self._pw.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=browser_headless,
            )
        else:
            self._browser = self._pw.chromium.launch(headless=browser_headless)
            self._context = self._browser.new_context()
        self._page: Page = self._context.new_page()

    @property
    def page(self) -> Page:
        return self._page

    def goto(self, url: str) -> Tuple[str, Optional[str]]:
        """URL로 이동. (final_url, error_reason) 반환.

        navigation interrupted 에러는 2초 대기 후 최대 2회 재시도.
        """
        MAX_RETRIES = 2
        for attempt in range(MAX_RETRIES + 1):
            try:
                self._page.goto(url, timeout=BROWSER_TIMEOUT_MS, wait_until="domcontentloaded")
                break
            except PlaywrightError as e:
                err_msg = str(e)
                if "interrupted by another navigation" in err_msg and attempt < MAX_RETRIES:
                    print(f"  [RETRY] navigation interrupted, 2초 후 재시도 ({attempt + 1}/{MAX_RETRIES})")
                    time.sleep(2)
                    continue
                return self._page.url, f"navigation_failed: {err_msg}"

        # SPA 페이지가 안정될 때까지 대기
        try:
            self._page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightError:
            pass  # networkidle 실패해도 계속 진행 (느린 페이지일 뿐)

        final_url = self._page.url

        # 로그인 필요 감지 우선 (Next.js SPA 포함)
        reason = _is_login_page(self._page)
        if reason:
            return final_url, reason

        # 그 외 차단 감지 (캡차, 권한 없음 등)
        blocked = check_blocked(final_url, self._page.content())
        if blocked:
            return final_url, blocked
        return final_url, None

    def get_frame_html(self) -> Tuple[Optional[str], Optional[str]]:
        """cafe_main iframe HTML 반환. (html, error_reason)"""
        MAX_RETRIES = 2
        for attempt in range(MAX_RETRIES + 1):
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
                err_msg = str(e)
                if "is navigating" in err_msg and attempt < MAX_RETRIES:
                    print(f"  [RETRY] 페이지 navigating 중, 2초 후 재시도 ({attempt + 1}/{MAX_RETRIES})")
                    time.sleep(2)
                    try:
                        self._page.wait_for_load_state("networkidle", timeout=10000)
                    except PlaywrightError:
                        pass
                    continue
                return None, f"frame_load_failed: {err_msg}"

    def screenshot(self, path: str) -> None:
        try:
            self._page.screenshot(path=path, full_page=True)
        except PlaywrightError:
            pass

    def close(self) -> None:
        # page → context → browser → pw 순으로 단계별 종료 (pending task hang 방지)
        close_steps = [self._page.close, self._context.close]
        if self._browser is not None:
            close_steps.append(self._browser.close)
        close_steps.append(self._pw.stop)
        for fn in close_steps:
            try:
                fn()
            except Exception:
                pass


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
