"""scripts/diag_block_pattern.py

_BLOCK_CONTENT 패턴 각각이 article 218 페이지 HTML의 어느 위치에서 매치되는지
컨텍스트와 함께 출력하는 진단 스크립트.

false positive 판별 목적이므로 기존 파일은 수정하지 않고 읽기 전용으로 임포트.
"""
import sys
import time

sys.path.insert(0, "src")

from browser import _BLOCK_CONTENT, BrowserSession, wait_for_login
from config import DEBUG_DIR
from db import get_article_by_id

ARTICLE_ID = 218
CONTEXT_CHARS = 80
MAX_MATCHES_PER_PATTERN = 5

CAFE_MEMBERS_URL = (
    "https://cafe.naver.com/f-e/cafes/29082876/members/"
    "THEA7uBzD6uKXKno57_Bl7jItzRnvmuDMltnPsGI9BY"
)


def find_matches(text: str, pattern: str) -> list[int]:
    """pattern이 text에서 등장하는 모든 시작 인덱스 반환."""
    positions = []
    start = 0
    while True:
        idx = text.find(pattern, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def print_match_context(html: str, pattern: str, idx: int, match_num: int) -> None:
    before_start = max(0, idx - CONTEXT_CHARS)
    after_end = min(len(html), idx + len(pattern) + CONTEXT_CHARS)

    before = html[before_start:idx]
    matched = html[idx: idx + len(pattern)]
    after = html[idx + len(pattern): after_end]

    # 비가시 문자 치환해서 읽기 쉽게
    before = before.replace("\n", "↵").replace("\r", "")
    after = after.replace("\n", "↵").replace("\r", "")

    print(f"  [Match {match_num} at index {idx:,}]")
    print(f"  ...{before}[{matched}]{after}...")
    print()


def scan_patterns(html: str) -> None:
    print()
    print("=" * 70)
    print("  _BLOCK_CONTENT 패턴 매치 진단 (article_id=218)")
    print("=" * 70)

    for reason, pattern in _BLOCK_CONTENT:
        print()
        print(f'=== Pattern: "{pattern}"  (reason={reason}) ===')

        positions = find_matches(html, pattern)
        if not positions:
            print("  (no match)")
            continue

        shown = positions[:MAX_MATCHES_PER_PATTERN]
        for i, idx in enumerate(shown, 1):
            print_match_context(html, pattern, idx, i)

        if len(positions) > MAX_MATCHES_PER_PATTERN:
            print(f"  ... 외 {len(positions) - MAX_MATCHES_PER_PATTERN}건 생략 (총 {len(positions)}건)")

    print()
    print("=" * 70)
    print("  진단 완료")
    print("=" * 70)


def save_diagnostic_html(html: str, article_id: int) -> None:
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEBUG_DIR / f"diagnostic_{article_id}_block_pattern.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"[diag] HTML 저장 완료: {out_path}")
    except Exception as e:
        print(f"[diag] HTML 저장 실패: {e}")


def main() -> int:
    article = get_article_by_id(ARTICLE_ID)
    if article is None:
        print(f"[error] article_id={ARTICLE_ID} 가 DB에 없습니다.")
        return 1

    print(f"[diag] 대상: article_id={article.article_id}")
    print(f"[diag] title: {article.title[:60] if article.title else '(none)'}")
    print(f"[diag] url:   {article.url}")
    print(f"[diag] status: {article.status}")
    print()

    print("[diag] 브라우저 세션 시작...")
    session = BrowserSession()

    try:
        # 카페 멤버 페이지 진입 — 비로그인 시 nid.naver.com 으로 redirect → 로그인 대기
        print(f"[diag] 카페 멤버 페이지 진입: {CAFE_MEMBERS_URL}")
        session.goto(CAFE_MEMBERS_URL)

        wait_for_login(session.page)

        # 게시글 페이지 진입
        print(f"[diag] 게시글 페이지 진입: {article.url}")
        session.goto(article.url)

        # slow crawl — 3~5초 대기
        print("[diag] 페이지 안정화 대기 (4초)...")
        time.sleep(4)

        # 전체 페이지 HTML 수집 (프레임 포함 외부 페이지 전체)
        html = session.page.content()
        print(f"[diag] page.content() 길이: {len(html):,} bytes")

        # 진단 HTML 저장
        save_diagnostic_html(html, ARTICLE_ID)

        # 패턴별 매치 분석 출력
        scan_patterns(html)

        return 0

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
