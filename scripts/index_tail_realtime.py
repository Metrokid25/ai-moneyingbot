"""scripts/index_tail.py — 끝페이지 자동 감지 후 tail N페이지 인덱싱.

사용법:
    python scripts/index_tail.py "<목록_URL>" [--estimate 2828] [--tail 3]
    python scripts/index_tail.py "<목록_URL>" --collect-after-snapshot

끝페이지 탐색 알고리즘:
  - estimate 페이지에 글 있음 → +1씩 전진, 빈 페이지 직전이 tail
  - estimate 페이지가 빈 결과 → -1씩 후퇴, 첫 글 있는 페이지가 tail

스냅샷:
  - 양산 시작 시 페이지 1을 fetch해 최고 article_id를 기록 (data/snapshot_<ts>.json)
  - 양산 중 스냅샷보다 큰 article_id는 무시 (새로 올라온 글)
  - --collect-after-snapshot: 양산 완료 후 스냅샷 이후 신규 글만 수집
"""
import argparse
import datetime
import json
import random
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, "src")

from browser import BrowserSession, check_blocked, wait_for_login
from db import get_conn, init_db, upsert_article, article_exists
from indexer import build_page_url
from member_api import NAVER_LOGIN_URL, fetch_member_articles, parse_member_list_url
from models import Article
from parser import parse_article_list

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SNAPSHOT_DIR = _PROJECT_ROOT / "data"

SCAN_FORWARD_MAX = 15   # estimate에서 최대 전진 폭
SCAN_BACKWARD_MAX = 50  # estimate에서 최대 후퇴 폭
INTERACTIVE_LOGIN_RETRIES = 3


# ── 스냅샷 유틸 ───────────────────────────────────────────────────────────────

def _is_login_required_error(err) -> bool:
    if err is None:
        return False
    text = str(err).lower()
    return "login_required" in text or "login" in text or "로그인" in str(err)


def _console_enter_wait(prompt: str) -> None:
    """콘솔 안전 Enter 대기. Windows PowerShell에서 input()이 stdin EOF로
    즉시 통과하는 문제(browser.wait_for_login과 동일)를 msvcrt로 우회."""
    print(prompt, flush=True)
    if sys.platform == "win32":
        import msvcrt
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                break
    else:
        sys.stdin.readline()


def _wait_for_interactive_login(input_func=None) -> None:
    print("[index_tail] login_required detected.")
    print("[index_tail] 브라우저에 연 네이버 로그인 페이지에서 직접 로그인하세요.")
    print("[index_tail] CAPTCHA/본인인증이 뜨면 사용자가 직접 처리해야 합니다.")
    print("[index_tail] 로그인이 완료되면 PowerShell에서 Enter를 누르세요.")
    if input_func is None:
        input_func = _console_enter_wait
    input_func("[index_tail] Enter를 누르면 같은 브라우저 세션으로 다시 확인합니다...")


def _fetch_rows_with_interactive_login(
    session: "BrowserSession",
    list_url: str,
    page_num: int,
    *,
    interactive_login: bool = False,
    input_func=None,
    max_retries: int = INTERACTIVE_LOGIN_RETRIES,
):
    attempts = 0
    while True:
        rows, err = _fetch_rows(session, list_url, page_num)
        if not interactive_login or not _is_login_required_error(err):
            return rows, err
        if attempts >= max_retries:
            return rows, err
        attempts += 1
        # 멤버 목록 SPA는 비로그인 시 빈 셸만 보여서 로그인 폼이 안 뜸 →
        # 네이버 로그인 페이지를 직접 열어 사용자가 바로 로그인할 수 있게 한다.
        # goto는 에러를 반환값으로 주며, 로그인 페이지 자체는 'login_required'로
        # 감지되는 게 정상. 그 외 실패(navigation_failed 등)는 경고로 알린다.
        try:
            _login_url, login_nav_err = session.goto(NAVER_LOGIN_URL)
            if login_nav_err and "login" not in str(login_nav_err):
                print(f"[index_tail] WARN: 로그인 페이지 열기 실패({login_nav_err}) — 브라우저 상태를 확인하세요.")
        except Exception as e:
            print(f"[index_tail] WARN: 로그인 페이지 열기 중 예외({e}) — 브라우저 상태를 확인하세요.")
        _wait_for_interactive_login(input_func=input_func)
        print(f"[index_tail] 같은 브라우저 세션으로 page {page_num} 재확인 ({attempts}/{max_retries})")


def _get_db_max_id() -> Optional[int]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT MAX(article_id) FROM articles").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _create_snapshot(
    session: "BrowserSession",
    list_url: str,
    *,
    interactive_login: bool = False,
    input_func=None,
) -> Optional[dict]:
    """페이지 1 fetch → 최고 article_id 스냅샷 생성 후 data/snapshot_<ts>.json 저장."""
    rows, err = _fetch_rows_with_interactive_login(
        session,
        list_url,
        1,
        interactive_login=interactive_login,
        input_func=input_func,
    )
    if err or not rows:
        print(f"[snapshot] 페이지 1 fetch 실패: {err}")
        return None

    snapshot_max_id = max(r["article_id"] for r in rows)
    db_max_id = _get_db_max_id()
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    snapshot = {
        "created_at": ts,
        "snapshot_max_id": snapshot_max_id,
        "db_max_id_at_snapshot": db_max_id,
    }

    _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = _SNAPSHOT_DIR / f"snapshot_{ts}.json"
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[snapshot] 저장: {path.name}")
    print(f"[snapshot] snapshot_max_id={snapshot_max_id}  db_max_id={db_max_id}")
    return snapshot


def _load_latest_snapshot() -> Optional[dict]:
    """data/snapshot_*.json 중 가장 최근 파일을 로드."""
    snapshots = sorted(_SNAPSHOT_DIR.glob("snapshot_*.json"))
    if not snapshots:
        return None
    data = json.loads(snapshots[-1].read_text(encoding="utf-8"))
    print(f"[snapshot] 로드: {snapshots[-1].name}  snapshot_max_id={data.get('snapshot_max_id')}")
    return data


def _collect_after_snapshot(
    session: "BrowserSession",
    list_url: str,
    min_id: int,
    *,
    interactive_login: bool = False,
    input_func=None,
    stop_after_empty_pages: Optional[int] = None,
):
    """min_id 이상인 신규 글만 page 1부터 순방향 수집.

    article_id < min_id 글을 처음 만나는 순간 수집 종료.
    (total, stop_err) 반환 — stop_err은 차단(login_required 등)으로 중단됐을 때의
    에러 문자열. 정상 종료면 None. 호출부는 stop_err 시 성공으로 위장하면 안 된다.
    """
    total = 0
    page = 1
    empty_save_pages = 0
    stop_err = None
    while True:
        page_url = build_page_url(list_url, page)
        print(f"\n[after-snapshot][PAGE {page}] {page_url}")

        rows, err = _fetch_rows_with_interactive_login(
            session,
            list_url,
            page,
            interactive_login=interactive_login,
            input_func=input_func,
        )
        if err:
            print(f"  [STOP] 차단 감지: {err}")
            stop_err = err
            break

        if not rows:
            print(f"  [STOP] 빈 페이지 또는 파싱 실패")
            break

        reached_old = False
        new_cnt = 0
        for row in rows:
            if row["article_id"] < min_id:
                # 스냅샷 이전 글에 도달 → 더 이상 신규 글 없음
                reached_old = True
                break
            if article_exists(row["article_id"]):
                continue
            upsert_article(Article(
                article_id=row["article_id"],
                url=row["url"],
                title=row["title"],
                author="굿머닝",
                posted_at=row["posted_at"],
                source_page=page,
                status="INDEXED",
            ))
            new_cnt += 1

        total += new_cnt
        print(f"  저장: {new_cnt}개  (누적: {total}개)")

        if reached_old:
            print(f"  [after-snapshot] 스냅샷 이전 글 도달, 수집 완료")
            break

        if stop_after_empty_pages is not None:
            if new_cnt == 0:
                empty_save_pages += 1
                if empty_save_pages >= stop_after_empty_pages:
                    print(
                        "  [after-snapshot][realtime] "
                        f"saved 0 for {empty_save_pages} consecutive pages, stop"
                    )
                    break
            else:
                empty_save_pages = 0

        _sleep()
        page += 1

    return total, stop_err


def _sleep() -> None:
    delay = random.uniform(3.0, 5.0)
    print(f"  [{delay:.1f}초 대기]")
    time.sleep(delay)


def _fetch_rows(session: BrowserSession, list_url: str, page_num: int):
    """(rows_or_None, err_or_None) 반환."""
    # 2026-07-02: 멤버 작성글 목록 페이지가 SPA(클라이언트 렌더)로 바뀌어
    # HTML 파싱이 0행이 됨 → 멤버 목록 URL이면 REST API를 직접 호출한다.
    member = parse_member_list_url(list_url)
    if member is not None:
        cafe_id, member_key = member
        return fetch_member_articles(session, cafe_id, member_key, page_num)
    # 멤버 목록 URL이 아니면 기존 HTML 파싱 경로 유지
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


def find_tail(
    session: BrowserSession,
    list_url: str,
    estimate: int,
    *,
    interactive_login: bool = False,
    input_func=None,
):
    """끝페이지 번호 반환 (None=감지 실패)."""
    print(f"\n[tail_scan] estimate={estimate} 에서 탐색 시작...")

    rows, err = _fetch_rows_with_interactive_login(
        session,
        list_url,
        estimate,
        interactive_login=interactive_login,
        input_func=input_func,
    )
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
            rows, err = _fetch_rows_with_interactive_login(
                session,
                list_url,
                page,
                interactive_login=interactive_login,
                input_func=input_func,
            )
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
        rows, err = _fetch_rows_with_interactive_login(
            session,
            list_url,
            page,
            interactive_login=interactive_login,
            input_func=input_func,
        )
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


def index_pages(
    session: BrowserSession,
    list_url: str,
    pages: list[int],
    snapshot_max_id: Optional[int] = None,
    *,
    interactive_login: bool = False,
    input_func=None,
) -> int:
    """pages 목록을 순서대로 인덱싱. 저장 건수 반환.

    snapshot_max_id가 지정되면 그보다 큰 article_id는 무시 (양산 중 신규 글 차단).
    """
    total = 0
    for page_num in pages:
        page_url = build_page_url(list_url, page_num)
        print(f"\n[PAGE {page_num}] {page_url}")

        rows, err = _fetch_rows_with_interactive_login(
            session,
            list_url,
            page_num,
            interactive_login=interactive_login,
            input_func=input_func,
        )
        if not rows:
            print(f"  [WARN] 글 행 파싱 실패 또는 빈 페이지, 스킵")
            _sleep()
            continue

        new_cnt = skip_cnt = snap_skip_cnt = 0
        for row in rows:
            if snapshot_max_id is not None and row["article_id"] > snapshot_max_id:
                snap_skip_cnt += 1
                continue
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
        snap_info = f"  스냅샷스킵: {snap_skip_cnt}개" if snap_skip_cnt else ""
        print(f"  저장: {new_cnt}개  스킵: {skip_cnt}개{snap_info}  (누적: {total}개)")
        _sleep()

    return total


def run_realtime_index(
    list_url: str,
    session: BrowserSession,
    *,
    interactive_login: bool = False,
    stop_after_empty_pages: Optional[int] = None,
) -> int:
    """Run the realtime collect-after-snapshot path using an existing session."""
    print(f"[index_tail] url     : {list_url}")

    init_db()

    snapshot = _load_latest_snapshot()
    if snapshot is None:
        print("[index_tail] ERROR: data/snapshot_*.json not found.")
        return 1

    min_id = snapshot["snapshot_max_id"] + 1
    print(f"[index_tail] --collect-after-snapshot: article_id >= {min_id}")

    # 멤버 목록 URL은 REST API로 수집하므로 (죽은 SPA 셸) 페이지 진입이 불필요.
    # 로그인 필요 여부는 API의 login_required 감지 → 재시도 흐름에서 처리된다.
    if parse_member_list_url(list_url) is None:
        trigger_url = build_page_url(list_url, 1)
        print(f"\n[index_tail] browser entry: {trigger_url}")
        _final_url, entry_err = session.goto(trigger_url)
        if interactive_login:
            if entry_err == "login_required":
                print("[LOGIN] 브라우저에서 로그인을 완료한 뒤, 이 PowerShell 창에서 엔터를 눌러주세요.", flush=True)
                print("[LOGIN] 엔터 입력 대기 중...", flush=True)
            wait_for_login(session.page)
    else:
        print("[index_tail] member-list URL: REST API로 수집 (browser entry 생략)")

    total, stop_err = _collect_after_snapshot(
        session,
        list_url,
        min_id,
        interactive_login=interactive_login,
        stop_after_empty_pages=stop_after_empty_pages,
    )
    if stop_err:
        # 'complete'를 찍지 않는다 — 루프(run_daily_archive_loop)가 이 신호로
        # 본문수집 스킵/정지 사유 판정을 한다. 성공 위장 금지.
        print(f"\n[index_tail] stopped: {stop_err}  saved={total}")
        return 1
    print(f"\n[index_tail] complete. saved={total}")
    return 0


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
    ap.add_argument(
        "--collect-after-snapshot",
        action="store_true",
        help="최근 스냅샷 이후 신규 글(article_id > snapshot_max_id)만 수집",
    )
    ap.add_argument(
        "--interactive-login",
        action="store_true",
        help="login_required 발생 시 브라우저를 유지하고 사용자의 수동 로그인/Enter 후 같은 세션으로 재시도",
    )
    ap.add_argument(
        "--stop-after-empty-pages",
        type=int,
        default=None,
        help="Realtime experiment: stop after N consecutive pages save 0 new articles.",
    )
    args = ap.parse_args()

    print(f"[index_tail] url     : {args.url}")

    init_db()

    session = BrowserSession()
    try:
        # ── --collect-after-snapshot 모드 ─────────────────────────────────
        if args.collect_after_snapshot:
            return run_realtime_index(
                args.url,
                session,
                interactive_login=args.interactive_login,
                stop_after_empty_pages=args.stop_after_empty_pages,
            )

        # ── 정상 양산 모드 ────────────────────────────────────────────────
        print(f"[index_tail] estimate: {args.estimate}")
        print(f"[index_tail] tail    : {args.tail}")

        # 로그인 트리거 — estimate 페이지로 직진 (멤버 목록 URL은 API 수집이라 생략)
        if parse_member_list_url(args.url) is None:
            trigger_url = build_page_url(args.url, args.estimate)
            print(f"\n[index_tail] 브라우저 진입: {trigger_url}")
            session.goto(trigger_url)
            if args.interactive_login:
                wait_for_login(session.page)
        else:
            print("[index_tail] member-list URL: REST API로 수집 (browser entry 생략)")

        # 스냅샷 생성 (페이지 1 fetch → 최고 article_id 기록)
        snapshot = _create_snapshot(
            session,
            args.url,
            interactive_login=args.interactive_login,
        )
        snapshot_max_id = snapshot["snapshot_max_id"] if snapshot else None
        if snapshot_max_id is None:
            print("[index_tail] WARN: 스냅샷 생성 실패, snapshot 필터 없이 진행")

        # 끝페이지 탐색
        tail = find_tail(
            session,
            args.url,
            args.estimate,
            interactive_login=args.interactive_login,
        )
        if tail is None:
            print("[index_tail] 끝페이지 탐색 실패, 종료")
            return 1

        print(f"\n[index_tail] ★ 끝페이지: {tail}")

        pages = [p for p in range(tail, tail - args.tail, -1) if p >= 1]
        print(f"[index_tail] 인덱싱 대상: {pages}")

        total = index_pages(
            session,
            args.url,
            pages,
            snapshot_max_id=snapshot_max_id,
            interactive_login=args.interactive_login,
        )
        print(f"\n[index_tail] 완료. 총 {total}개 저장")
        return 0

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
