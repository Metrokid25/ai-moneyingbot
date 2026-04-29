import argparse
import os
import random
import sys
import time

sys.path.insert(0, "src")

from browser import BrowserSession, wait_for_login
from collector import _VALID_SIMULATE, collect_body
from db import get_article_by_id, get_articles_by_status, get_conn
from models import Status

CAFE_MEMBERS_URL = (
    "https://cafe.naver.com/f-e/cafes/29082876/members/"
    "THEA7uBzD6uKXKno57_Bl7jItzRnvmuDMltnPsGI9BY"
)

SLEEP_BETWEEN_S = 3.0


def _print_summary(processed, total, retry_stats, status_counts, body_lens, failed_ids, elapsed_list):
    print()
    print("=" * 70)
    print(f"[batch] 처리 완료: {processed}/{total}")
    print(f"[batch] 신규 처리 (attempt_count 0→1): {retry_stats['new']}건")
    print(f"[batch] 재시도 (attempt_count >= 1):   {retry_stats['retry']}건")
    print(f"[batch] 성공 (BODY_COLLECTED):         {retry_stats['success']}건")
    print(f"[batch] INDEXED 유지 (transient):      {retry_stats['kept_indexed']}건")
    print(f"[batch] BODY_FAILED 강등:              {retry_stats['demoted']}건")
    print(f"[batch] status 분포: {dict(sorted(status_counts.items()))}")
    if body_lens:
        body_lens_sorted = sorted(body_lens)
        n = len(body_lens_sorted)
        median = body_lens_sorted[n // 2]
        avg = sum(body_lens_sorted) / n
        print(
            f"[batch] body_len (BODY_COLLECTED만, n={n}): "
            f"min={min(body_lens_sorted)}, median={median}, "
            f"max={max(body_lens_sorted)}, 평균={avg:.0f}"
        )
    if elapsed_list:
        avg_e = sum(elapsed_list) / len(elapsed_list)
        total_e = sum(elapsed_list)
        print(f"[batch] elapsed: 평균={avg_e:.1f}s, 총={total_e:.1f}s")
    if failed_ids:
        print(f"[batch] 실패/차단 article_ids ({len(failed_ids)}개): {failed_ids}")
    print("=" * 70)


def _print_error_reason_dist():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT last_error_reason, COUNT(*) as cnt "
            "FROM articles WHERE status='INDEXED' AND attempt_count > 0 "
            "GROUP BY last_error_reason ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return
    print("\n[batch] INDEXED 유지 글 last_error_reason 분포 (상위 10):")
    for reason, cnt in rows:
        print(f"  {cnt:>4}건  {reason}")


def _parse_args():
    p = argparse.ArgumentParser(description="INDEXED 글 일괄 본문 수집")
    p.add_argument(
        "--simulate-fail",
        choices=sorted(_VALID_SIMULATE),
        default=None,
        help="실패 주입 종류 (DEV_MODE=1 필수)",
    )
    p.add_argument(
        "--simulate-rate",
        type=float,
        default=1.0,
        help="simulate-fail 적용 확률 0.0~1.0 (기본 1.0 = 전체 적용)",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    if args.simulate_fail is not None and os.environ.get("DEV_MODE") != "1":
        print("[ERROR] --simulate-fail requires DEV_MODE=1")
        return 1

    indexed_articles = get_articles_by_status(Status.INDEXED)
    indexed_ids = [a.article_id for a in indexed_articles]
    total = len(indexed_ids)

    # 사전에 attempt_count 조회 (신규/재시도 분류용)
    attempt_counts_before: dict[int, int] = {}
    if total > 0:
        conn = get_conn()
        try:
            for a in indexed_articles:
                row = conn.execute(
                    "SELECT attempt_count FROM articles WHERE article_id=?", (a.article_id,)
                ).fetchone()
                attempt_counts_before[a.article_id] = row[0] if row else 0
        finally:
            conn.close()

    print(f"[batch] 대상: {total}건 INDEXED")
    print(f"[batch] article_ids: {indexed_ids}")

    if total == 0:
        print("[batch] 처리할 글 없음. 종료.")
        return 0

    if args.simulate_fail:
        print(f"[batch] simulate-fail={args.simulate_fail} rate={args.simulate_rate}")

    print(f"[batch] 예상 소요 시간: 약 {total * (8 + SLEEP_BETWEEN_S) / 60:.1f}분")
    print()
    print("[batch] 브라우저 세션 시작...")
    session = BrowserSession()

    status_counts: dict[str, int] = {}
    body_lens: list[int] = []
    failed_ids: list[int] = []
    elapsed_list: list[float] = []
    retry_stats = {"new": 0, "retry": 0, "success": 0, "kept_indexed": 0, "demoted": 0}
    processed = 0

    try:
        session.goto(CAFE_MEMBERS_URL)
        wait_for_login(session.page)

        for i, aid in enumerate(indexed_ids, 1):
            # 신규/재시도 분류
            before_count = attempt_counts_before.get(aid, 0)
            if before_count == 0:
                retry_stats["new"] += 1
            else:
                retry_stats["retry"] += 1

            # simulate_fail 확률 적용
            effective_sim = None
            if args.simulate_fail and random.random() < args.simulate_rate:
                effective_sim = args.simulate_fail

            t0 = time.time()
            exc = None
            try:
                collect_body(aid, session=session, simulate_fail=effective_sim)
            except Exception as e:
                exc = e
            elapsed = time.time() - t0
            elapsed_list.append(elapsed)

            if exc is not None:
                print(f"[batch] [{i}/{total}] article_id={aid} EXCEPTION ({elapsed:.1f}s): {exc}")
                status_counts["EXCEPTION"] = status_counts.get("EXCEPTION", 0) + 1
                failed_ids.append(aid)
            else:
                after = get_article_by_id(aid)
                status = after.status if after else "MISSING"
                body_len = len(after.clean_text) if after and after.clean_text else 0

                status_counts[status] = status_counts.get(status, 0) + 1

                if status == Status.BODY_COLLECTED:
                    retry_stats["success"] += 1
                    body_lens.append(body_len)
                elif status == Status.INDEXED:
                    retry_stats["kept_indexed"] += 1
                    failed_ids.append(aid)
                else:
                    retry_stats["demoted"] += 1
                    failed_ids.append(aid)

                print(
                    f"[batch] [{i}/{total}] article_id={aid} → "
                    f"status={status} len={body_len} elapsed={elapsed:.1f}s"
                )

            processed = i

            if i < total:
                time.sleep(SLEEP_BETWEEN_S)

    except KeyboardInterrupt:
        print(f"\n[batch] 사용자 중단. 처리 완료: {processed}/{total}")

    finally:
        _print_summary(processed, total, retry_stats, status_counts, body_lens, failed_ids, elapsed_list)
        _print_error_reason_dist()
        try:
            session.close()
        except Exception:
            pass

    return 0 if not failed_ids else 1


if __name__ == "__main__":
    sys.exit(main())
