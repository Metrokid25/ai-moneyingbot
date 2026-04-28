import sys
import time

sys.path.insert(0, "src")

from browser import BrowserSession, wait_for_login
from collector import collect_body
from db import get_article_by_id, get_articles_by_status
from models import Status

CAFE_MEMBERS_URL = (
    "https://cafe.naver.com/f-e/cafes/29082876/members/"
    "THEA7uBzD6uKXKno57_Bl7jItzRnvmuDMltnPsGI9BY"
)

SLEEP_BETWEEN_S = 3.0


def _print_summary(processed, total, status_counts, body_lens, failed_ids, elapsed_list):
    print()
    print("=" * 70)
    print(f"[batch] 처리 완료: {processed}/{total}")
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


def main() -> int:
    indexed_articles = get_articles_by_status(Status.INDEXED)
    indexed_ids = [a.article_id for a in indexed_articles]  # db already ORDER BY article_id
    total = len(indexed_ids)

    print(f"[batch] 대상: {total}건 INDEXED")
    print(f"[batch] article_ids: {indexed_ids}")

    if total == 0:
        print("[batch] 처리할 글 없음. 종료.")
        return 0

    print(f"[batch] 예상 소요 시간: 약 {total * (8 + SLEEP_BETWEEN_S) / 60:.1f}분 (건당 평균 8초 + 3초 sleep 가정)")
    print()
    print("[batch] 브라우저 세션 시작...")
    session = BrowserSession()

    status_counts: dict[str, int] = {}
    body_lens: list[int] = []
    failed_ids: list[int] = []
    elapsed_list: list[float] = []
    processed = 0

    try:
        session.goto(CAFE_MEMBERS_URL)
        wait_for_login(session.page)

        for i, aid in enumerate(indexed_ids, 1):
            t0 = time.time()
            exc = None
            try:
                collect_body(aid, session=session)
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
                    body_lens.append(body_len)
                else:
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
        _print_summary(processed, total, status_counts, body_lens, failed_ids, elapsed_list)
        try:
            session.close()
        except Exception:
            pass

    return 0 if not failed_ids else 1


if __name__ == "__main__":
    sys.exit(main())
