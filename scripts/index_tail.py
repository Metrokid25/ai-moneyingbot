"""scripts/index_tail.py — 끝페이지 자동 감지 후 tail N페이지 인덱싱.

사용법:
    python scripts/index_tail.py "<목록_URL>" [--estimate 2828] [--tail 3]

끝페이지 탐색 알고리즘:
  - estimate 페이지에 글 있음 → +1씩 전진, 빈 페이지 직전이 tail
  - estimate 페이지가 빈 결과 → -1씩 후퇴, 첫 글 있는 페이지가 tail
"""
import argparse
import random
import sys
import time

sys.path.insert(0, "src")

from browser import BrowserSession, check_blocked, wait_for_login
from db import init_db, upsert_article, article_exists
from indexer import build_page_url
from models import Article
from parser import parse_article_list

SCAN_FORWARD_MAX = 15   # estimate에서 최대 전진 폭
SCAN_BACKWARD_MAX = 50  # estimate에서 최대 후퇴 폭


def _sleep() -> None:
    delay = random.uniform(3.0, 5.0)
    print(f"  [{delay:.1f}초 대기]")
    time.sleep(delay)


def _fetch_rows(session: BrowserSession, list_url: str, page_num: int):
    """(rows_or_None, err_or_None) 반환."""
    page_url = build_page_url(list_url, page_num)
    final_url, err = session.goto(page_url)
    if err:
        return None, err
    html, frame_err = session.get_frame_html()
    if frame_err or html is None:
        return None, frame_err or "frame_load_failed"
    blocked = check_blocked(final_url, html)
    if blocked:
        return None, blocked
    rows = parse_article_list(html, final_url)
    return rows, None


def find_tail(session: BrowserSession, list_url: str, estimate: int):
    """끝페이지 번호 반환 (None=감지 실패)."""
    print(f"\n[tail_scan] estimate={estimate} 에서 탐색 시작...")

    rows, err = _fetch_rows(session, list_url, estimate)
    if err:
        print(f"[tail_scan] estimate 페이지 에러: {err}")
        return None

    if not rows:
        # estimate가 이미 끝 너머 → 후퇴
        print(f"[tail_scan] page {estimate} 빈 결과 → 후퇴 탐색")
        for back in range(1, SCAN_BACKWARD_MAX + 1):
            page = estimate - back
            if page < 1:
                break
            _sleep()
            rows, err = _fetch_rows(session, list_url, page)
            if err:
                print(f"[tail_scan] page {page} 에러: {err}, 계속 후퇴...")
                continue
            if rows:
                print(f"[tail_scan] 끝페이지 확정: {page} ({len(rows)}건)")
                return page
            print(f"[tail_scan] page {page} 빈 결과, 계속 후퇴...")
        print(f"[tail_scan] 후퇴 한계({SCAN_BACKWARD_MAX}) 초과, 탐색 실패")
        return None

    # estimate에 결과 있음 → 전진
    last_good = estimate
    print(f"[tail_scan] page {estimate} 존재 ({len(rows)}건), 전진...")
    for fwd in range(1, SCAN_FORWARD_MAX + 1):
        page = estimate + fwd
        _sleep()
        rows, err = _fetch_rows(session, list_url, page)
        if err:
            print(f"[tail_scan] page {page} 에러: {err}, 여기서 중단")
            break
        if not rows:
            print(f"[tail_scan] page {page} 빈 결과 → 끝페이지 확정: {last_good}")
            return last_good
        last_good = page
        print(f"[tail_scan] page {page} 존재 ({len(rows)}건), 계속 전진...")

    print(f"[tail_scan] 전진 한계 도달. 마지막 확인 페이지: {last_good}")
    return last_good


def index_pages(session: BrowserSession, list_url: str, pages: list[int]) -> int:
    """pages 목록을 순서대로 인덱싱. 저장 건수 반환."""
    total = 0
    for page_num in pages:
        page_url = build_page_url(list_url, page_num)
        print(f"\n[PAGE {page_num}] {page_url}")

        final_url, err = session.goto(page_url)
        if err:
            print(f"  [STOP] 차단 감지: {err}")
            break

        html, frame_err = session.get_frame_html()
        if frame_err or html is None:
            print(f"  [STOP] 프레임 로드 실패: {frame_err}")
            break

        blocked = check_blocked(final_url, html or "")
        if blocked:
            print(f"  [STOP] 차단 감지 (iframe): {blocked}")
            break

        rows = parse_article_list(html, final_url)
        if not rows:
            print(f"  [WARN] 글 행 파싱 실패 또는 빈 페이지, 스킵")
            _sleep()
            continue

        new_cnt = skip_cnt = 0
        for row in rows:
            if article_exists(row["article_id"]):
                skip_cnt += 1
                continue
            upsert_article(Article(
                article_id=row["article_id"],
                url=row["url"],
                title=row["title"],
                author="굿머닝",
                posted_at=row["posted_at"],
                source_page=page_num,
                status="INDEXED",
            ))
            new_cnt += 1

        total += new_cnt
        print(f"  저장: {new_cnt}개  스킵: {skip_cnt}개  (누적: {total}개)")
        _sleep()

    return total


def main() -> int:
    ap = argparse.ArgumentParser(
        description="끝페이지 자동 감지 후 tail N 페이지 인덱싱"
    )
    ap.add_argument("url", help="굿머닝 작성글 목록 URL (page=N 파라미터 포함 형태)")
    ap.add_argument(
        "--estimate", type=int, default=2828,
        help="끝페이지 추정값 (기본값: 2828)",
    )
    ap.add_argument(
        "--tail", type=int, default=3,
        help="인덱싱할 tail 페이지 수 (기본값: 3)",
    )
    args = ap.parse_args()

    print(f"[index_tail] url     : {args.url}")
    print(f"[index_tail] estimate: {args.estimate}")
    print(f"[index_tail] tail    : {args.tail}")

    init_db()

    session = BrowserSession()
    try:
        # 로그인 트리거 — estimate 페이지로 직진
        trigger_url = build_page_url(args.url, args.estimate)
        print(f"\n[index_tail] 브라우저 진입: {trigger_url}")
        session.goto(trigger_url)

        wait_for_login(session.page)

        # 끝페이지 탐색 (_fetch_rows 내부에서 goto 처리)
        tail = find_tail(session, args.url, args.estimate)
        if tail is None:
            print("[index_tail] 끝페이지 탐색 실패, 종료")
            return 1

        print(f"\n[index_tail] ★ 끝페이지: {tail}")

        pages = [p for p in range(tail, tail - args.tail, -1) if p >= 1]
        print(f"[index_tail] 인덱싱 대상: {pages}")

        total = index_pages(session, args.url, pages)
        print(f"\n[index_tail] 완료. 총 {total}개 저장")
        return 0

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
