import argparse
import datetime
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")

from browser import BrowserSession, wait_for_login
from collector import _VALID_SIMULATE, collect_body
from db import get_article_by_id, get_articles_by_status, get_conn
from models import Status

CAFE_MEMBERS_URL = (
    "https://cafe.naver.com/f-e/cafes/29082876/members/"
    "THEA7uBzD6uKXKno57_Bl7jItzRnvmuDMltnPsGI9BY"
)

SLEEP_MIN_S = 3.0
SLEEP_MAX_S = 5.0
LOGS_DIR = Path("logs")
TOTAL_ARTICLES_SCALE = 42_386

# timeout:10, navigation:5, empty:3, session:0 → total 18
_SIM_PLAN = [("timeout", 10), ("navigation", 5), ("empty", 3)]


def _build_sim_map(indexed_ids: list[int]) -> dict[int, str]:
    """INDEXED 목록(ASC)에서 18건 균등 추출 → {article_id: fail_type}.

    각 구간 중간점을 선택해 ASC 첫/끝 건을 시뮬 대상에서 제외한다.
    공식: idx = (slot * n + n // 2) // total_slots
    """
    n = len(indexed_ids)
    total_slots = sum(cnt for _, cnt in _SIM_PLAN)
    sim_map: dict[int, str] = {}
    slot = 0
    for fail_type, count in _SIM_PLAN:
        for _ in range(count):
            idx = (slot * n + n // 2) // total_slots
            sim_map[indexed_ids[idx]] = fail_type
            slot += 1
    return sim_map


def _open_logfile() -> tuple[Path, object]:
    LOGS_DIR.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOGS_DIR / f"batch_recollect_{ts}.log"
    fh = open(path, "w", encoding="utf-8", buffering=1)
    return path, fh


def _log(fh, line: str) -> None:
    fh.write(line + "\n")


def _write_log_header(fh, total: int, sim_map: dict[int, str]) -> None:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _log(fh, f"[batch] 실행 시작: {now}")
    _log(fh, f"[batch] 대상: {total}건 INDEXED")
    if sim_map:
        _log(fh, "")
        _log(fh, "=== SIM INJECTION MAP ===")
        for aid in sorted(sim_map):
            _log(fh, f"  article_id={aid} type={sim_map[aid]}")
        _log(fh, "=== END MAP ===")
        _log(fh, "")


def _write_checkpoint(
    fh, i: int, total: int, success: int, failed_cnt: int, start_ts: float
) -> None:
    elapsed = time.time() - start_ts
    line = (
        f"[CHECKPOINT {i}/{total}] "
        f"success={success} failed={failed_cnt} "
        f"elapsed={elapsed:.0f}s ({elapsed / 60:.1f}min)"
    )
    _log(fh, line)
    print(line)


def _write_final_report(
    fh,
    processed: int,
    total: int,
    retry_stats: dict,
    sim_stats: dict,
    start_ts: float,
    end_ts: float,
) -> None:
    total_elapsed = end_ts - start_ts
    success = retry_stats["success"]
    demoted = retry_stats["demoted"]
    sim_injected = sim_stats["injected"]
    sim_success = sim_stats["success"]

    conn = get_conn()
    try:
        err_rows = conn.execute(
            "SELECT last_error_reason, COUNT(*) as cnt "
            "FROM articles WHERE attempt_count > 0 "
            "GROUP BY last_error_reason ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
    finally:
        conn.close()

    start_str = datetime.datetime.fromtimestamp(start_ts).strftime("%H:%M:%S")
    end_str = datetime.datetime.fromtimestamp(end_ts).strftime("%H:%M:%S")

    lines = [
        "",
        "=" * 70,
        "=== 종료 리포트 ===",
        (
            f"1. 성공률       : {success}/{total} ({success / total * 100:.1f}%)"
            if total else "1. 성공률       : N/A"
        ),
        (
            f"2. 실실패율     : {demoted}/{total} "
            "(단일 패스 한계 — 5회 누적 필요, 양산 자연 발생 시 검증)"
        ),
    ]

    if sim_injected > 0:
        rate_str = f"{sim_success}/{sim_injected} ({sim_success / sim_injected * 100:.0f}%)"
    else:
        rate_str = "N/A (시뮬 주입 없음)"
    lines.append(
        f"3. 재시도 성공률: {rate_str} (단일 패스 — transient 건 즉시 재시도 없음)"
    )

    lines += [
        f"4. 처리시간     : 시작={start_str}  종료={end_str}  총={total_elapsed / 60:.1f}분",
        "5. error_reason 분포:",
    ]
    if err_rows:
        for reason, cnt in err_rows:
            lines.append(f"     {cnt:>4}건  {reason}")
    else:
        lines.append("     (없음)")

    if processed > 0:
        scale_h = (total_elapsed / processed) * TOTAL_ARTICLES_SCALE / 3600
        lines.append(
            f"6. 양산 예상시간: {TOTAL_ARTICLES_SCALE:,}건 기준 약 {scale_h:.1f}시간"
            f" ({scale_h * 60:.0f}분)"
        )
    else:
        lines.append("6. 양산 예상시간: N/A (처리 건수 없음)")

    lines.append("=" * 70)

    for line in lines:
        _log(fh, line)
        print(line)


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
        help="실패 주입 종류 (DEV_MODE=1 필수, --inject-sim과 상호배타)",
    )
    p.add_argument(
        "--simulate-rate",
        type=float,
        default=1.0,
        help="simulate-fail 적용 확률 0.0~1.0 (기본 1.0 = 전체 적용)",
    )
    p.add_argument(
        "--inject-sim",
        action="store_true",
        help="18건 균등 분산 시뮬레이션 주입 (DEV_MODE=1 필수, --simulate-fail과 상호배타)",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    if args.inject_sim and args.simulate_fail:
        print("[ERROR] --inject-sim and --simulate-fail are mutually exclusive")
        return 1

    if (args.simulate_fail or args.inject_sim) and os.environ.get("DEV_MODE") != "1":
        print("[ERROR] simulation flags require DEV_MODE=1")
        return 1

    indexed_articles = get_articles_by_status(Status.INDEXED)
    indexed_ids = [a.article_id for a in indexed_articles]
    total = len(indexed_ids)

    sim_map: dict[int, str] = {}
    if args.inject_sim and total > 0:
        sim_map = _build_sim_map(indexed_ids)

    log_path, log_fh = _open_logfile()
    print(f"[batch] logfile: {log_path}")
    _write_log_header(log_fh, total, sim_map)

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
        log_fh.close()
        return 0

    if args.simulate_fail:
        print(f"[batch] simulate-fail={args.simulate_fail} rate={args.simulate_rate}")
    if sim_map:
        plan_str = ", ".join(f"{ft}:{cnt}" for ft, cnt in _SIM_PLAN)
        print(f"[batch] inject-sim: {len(sim_map)}건 ({plan_str})")

    avg_sleep = (SLEEP_MIN_S + SLEEP_MAX_S) / 2
    print(f"[batch] 예상 소요 시간: 약 {total * (8 + avg_sleep) / 60:.1f}분")
    print()
    print("[batch] 브라우저 세션 시작...")
    session = BrowserSession()

    status_counts: dict[str, int] = {}
    body_lens: list[int] = []
    failed_ids: list[int] = []
    elapsed_list: list[float] = []
    retry_stats = {"new": 0, "retry": 0, "success": 0, "kept_indexed": 0, "demoted": 0}
    sim_stats = {"injected": 0, "success": 0}
    processed = 0
    start_ts = time.time()

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

            # effective_sim 결정
            if sim_map:
                effective_sim = sim_map.get(aid)
            elif args.simulate_fail and random.random() < args.simulate_rate:
                effective_sim = args.simulate_fail
            else:
                effective_sim = None

            if effective_sim is not None:
                sim_stats["injected"] += 1

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
                    if effective_sim is not None:
                        sim_stats["success"] += 1
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

            if i % 100 == 0:
                _write_checkpoint(
                    log_fh, i, total,
                    retry_stats["success"],
                    retry_stats["kept_indexed"] + retry_stats["demoted"],
                    start_ts,
                )

            if i < total:
                time.sleep(random.uniform(SLEEP_MIN_S, SLEEP_MAX_S))

    except KeyboardInterrupt:
        print(f"\n[batch] 사용자 중단. 처리 완료: {processed}/{total}")

    finally:
        end_ts = time.time()
        _print_summary(processed, total, retry_stats, status_counts, body_lens, failed_ids, elapsed_list)
        _print_error_reason_dist()
        _write_final_report(log_fh, processed, total, retry_stats, sim_stats, start_ts, end_ts)
        try:
            log_fh.close()
        except Exception:
            pass
        try:
            session.close()
        except Exception:
            pass

    return 0 if not failed_ids else 1


if __name__ == "__main__":
    sys.exit(main())
