"""굿머닝 작성글 목록 인덱서.

사용법:
    python src/indexer.py <목록_URL> --start 2826 --end 1
"""
import argparse
import random
import time
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

from browser import BrowserSession, check_blocked, wait_for_login
from config import DEBUG_DIR
from db import init_db, upsert_article, article_exists
from models import Article
from parser import parse_article_list


def build_page_url(base_url: str, page: int) -> str:
    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["page"] = [str(page)]
    new_query = urlencode({k: v[0] for k, v in qs.items()})
    return urlunparse(parsed._replace(query=new_query))


def save_debug(session: BrowserSession, page_num: int, html: str | None) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    if html:
        debug_html = DEBUG_DIR / f"page_{page_num}.html"
        debug_html.write_text(html, encoding="utf-8")
        print(f"  [DEBUG] HTML 저장 → {debug_html}")
    shot = DEBUG_DIR / f"page_{page_num}.png"
    session.screenshot(str(shot))
    print(f"  [DEBUG] 스크린샷 저장 → {shot}")


def run_indexer(list_url: str, start_page: int, end_page: int) -> None:
    init_db()
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    if start_page >= end_page:
        pages = range(start_page, end_page - 1, -1)
    else:
        pages = range(start_page, end_page + 1)

    total_pages = abs(start_page - end_page) + 1
    print(f"[INFO] 인덱싱 시작: {total_pages}페이지 ({start_page} → {end_page})")

    session = BrowserSession()
    indexed_total = 0
    first_page = True

    try:
        for page_num in pages:
            page_url = build_page_url(list_url, page_num)
            print(f"\n[PAGE {page_num}] {page_url}")

            final_url, err = session.goto(page_url)

            if first_page:
                if err == "login_required":
                    wait_for_login(session.page)
                    current_url = session.page.url
                    if page_url in current_url or current_url == page_url:
                        print(f"  [INFO] 사용자가 이미 목표 페이지에 도달함, goto 생략")
                        final_url = current_url
                        err = None
                    else:
                        final_url, err = session.goto(page_url)
                first_page = False

            if err:
                print(f"  [STOP] 차단 감지: {err}")
                break

            html, err = session.get_frame_html()
            if err:
                print(f"  [STOP] 프레임 로드 실패: {err}")
                break

            blocked = check_blocked(final_url, html or "")
            if blocked:
                print(f"  [STOP] 차단 감지 (iframe): {blocked}")
                break

            rows = parse_article_list(html, final_url)

            if not rows:
                print(f"  [WARN] 글 행 파싱 실패 — debug 폴더에 저장")
                save_debug(session, page_num, html)
                _sleep()
                continue

            new_count = 0
            skip_count = 0
            for row in rows:
                if article_exists(row["article_id"]):
                    skip_count += 1
                    continue

                article = Article(
                    article_id=row["article_id"],
                    url=row["url"],
                    title=row["title"],
                    author="굿머닝",
                    posted_at=row["posted_at"],
                    source_page=page_num,
                    status="INDEXED",
                )
                upsert_article(article)
                new_count += 1

            indexed_total += new_count
            print(f"  저장: {new_count}개  스킵: {skip_count}개  (누적: {indexed_total}개)")

            _sleep()

    finally:
        session.close()

    print(f"\n[완료] 총 {indexed_total}개 저장")


def _sleep() -> None:
    delay = random.uniform(3.0, 5.0)
    print(f"  [{delay:.1f}초 대기]")
    time.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(description="굿머닝 작성글 목록 인덱서")
    parser.add_argument("url", help="굿머닝 작성글 목록 URL")
    parser.add_argument("--start", type=int, default=1, help="시작 페이지 (기본값: 1)")
    parser.add_argument("--end",   type=int, default=1, help="끝 페이지 (기본값: 1)")
    args = parser.parse_args()

    run_indexer(args.url, args.start, args.end)


if __name__ == "__main__":
    main()
