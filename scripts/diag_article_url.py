import sys
sys.path.insert(0, "src")

from browser import BrowserSession, _is_login_page
from db import get_articles_by_status


def main():
    rows = get_articles_by_status("INDEXED")
    if not rows:
        print("[error] INDEXED 글 없음. 먼저 인덱싱하세요.")
        return 1

    target = rows[0]
    print(f"[diag] target: article_id={target.article_id}")
    print(f"[diag] target.url: {target.url}")
    print()

    print("[diag] BrowserSession 시작 (로그인 X, 그냥 goto 만)...")
    session = BrowserSession()

    try:
        print(f"[diag] session.goto({target.url}) 호출...")
        final_url, err = session.goto(target.url)

        print()
        print("─" * 70)
        print(f"[result] goto 반환: final_url={final_url}")
        print(f"[result] goto 반환: err={err!r}")
        print()
        print(f"[result] session.page.url (실제 도착): {session.page.url}")
        print()

        is_login = _is_login_page(session.page)
        print(f"[result] _is_login_page() 결과: {is_login!r}")
        print("─" * 70)

        try:
            html = session.page.content()
            print()
            print(f"[result] page.content() 길이: {len(html):,} bytes")
            print()
            print("[result] page.content() 앞 1500자 ↓")
            print("─" * 70)
            print(html[:1500])
            print("─" * 70)
        except Exception as e:
            print(f"[error] content() 실패: {e}")

        return 0

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
