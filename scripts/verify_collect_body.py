import re
import sys
import time

sys.path.insert(0, "src")

from browser import BrowserSession, wait_for_login
from collector import collect_body
from db import get_articles_by_status, get_article_by_id
from models import Status

CAFE_MEMBERS_URL = (
    "https://cafe.naver.com/f-e/cafes/29082876/members/"
    "THEA7uBzD6uKXKno57_Bl7jItzRnvmuDMltnPsGI9BY"
)


def main():
    # 1. INDEXED 글 목록 (전체)
    rows = get_articles_by_status("INDEXED")
    if not rows:
        print("[error] INDEXED 글이 없습니다. 먼저 인덱싱하세요.")
        return 1

    target = rows[0]  # 첫 번째 글로 검증
    print(f"[verify] 대상: article_id={target.article_id}")
    print(f"[verify] title: {target.title[:50] if target.title else '(none)'}")
    print(f"[verify] url:   {target.url}")
    print()

    # 2. 세션 띄우고 로그인
    print("[verify] 브라우저 세션 시작...")
    session = BrowserSession()

    try:
        # 3. 카페 멤버 페이지로 진입 — 비로그인 시 nid.naver.com 으로 redirect → wait_for_login 트리거
        print(f"[verify] 카페 멤버 페이지 진입: {CAFE_MEMBERS_URL}")
        session.goto(CAFE_MEMBERS_URL)

        # 4. 로그인 대기
        wait_for_login(session.page)

        # 5. collect_body() 호출 — 세션 주입
        print()
        print(f"[verify] collect_body({target.article_id}) 호출...")
        t0 = time.time()
        status, _ = collect_body(target.article_id, session=session)
        elapsed = time.time() - t0

        # 6. 결과
        after = get_article_by_id(target.article_id)
        body_len = len(after.clean_text) if after.clean_text else 0
        raw_html_bytes = len(after.raw_html) if after.raw_html else 0
        preview = after.clean_text[:300] if after.clean_text else "(empty)"
        preview = re.sub(r"\s+", " ", preview).strip()

        print()
        print("─" * 60)
        print(f"[result] status     : INDEXED → {after.status}")
        print(f"[result] body_len   : {body_len:,}자")
        print(f"[result] raw_html   : {raw_html_bytes:,} bytes")
        print(f"[result] preview    : {preview}")
        print(f"[result] elapsed    : {elapsed:.1f}초")
        print("─" * 60)

        return 0 if status == Status.BODY_COLLECTED else 1

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
