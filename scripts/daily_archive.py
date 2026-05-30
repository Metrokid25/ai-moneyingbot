"""Daily archive pipeline entry point.

Safety defaults:
- `--dry-run` uses mock articles and never touches production `data/`.
- `--execute` is required for bounded real collection.
- Running with no mode prints guidance and exits without collecting.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from db import article_exists, init_db, upsert_article  # noqa: E402
from models import Article, Status  # noqa: E402
from config import DEFAULT_BROWSER_PROFILE_DIR  # noqa: E402

KST = timezone(timedelta(hours=9))
DEFAULT_STATE_DIR = PROJECT_ROOT / "state"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "reports" / "daily"
DEFAULT_LIMIT = 10
DEFAULT_PAGE_LIMIT = 1
MAX_LIMIT = 100
MAX_PAGE_LIMIT = 10
DEFAULT_DELAY_SECONDS = 3.0


@dataclass
class DailyStats:
    discovered: int = 0
    duplicates: int = 0
    saved: int = 0
    failed: int = 0
    dry_run: bool = False
    mode: str = "dry-run"
    limit: int = DEFAULT_LIMIT
    page_limit: int | None = DEFAULT_PAGE_LIMIT
    failed_items: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def mode_safety_message(stats: DailyStats) -> str:
    if stats.dry_run:
        return "dry-run used mock data only; no browser, network, or archive DB writes."
    return "execute mode is bounded by --limit/--page-limit and requires --list-url from the CLI."


def now_kst() -> datetime:
    return datetime.now(KST)


def default_crawl_state() -> dict[str, Any]:
    return {
        "last_run_at": None,
        "last_article_id": None,
        "last_article_url": None,
        "total_runs": 0,
    }


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON file: {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"JSON root must be an object: {path}")
    merged = dict(default)
    merged.update(data)
    return merged


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as fh:
        tmp_path = Path(fh.name)
        fh.write(payload)
    tmp_path.replace(path)


def load_crawl_state(path: Path) -> dict[str, Any]:
    return load_json(path, default_crawl_state())


def save_crawl_state(path: Path, state: dict[str, Any]) -> None:
    atomic_write_json(path, state)


def default_failed_queue() -> dict[str, Any]:
    return {"items": []}


def load_failed_queue(path: Path) -> dict[str, Any]:
    queue = load_json(path, default_failed_queue())
    if not isinstance(queue.get("items"), list):
        raise RuntimeError(f"failed queue items must be a list: {path}")
    return queue


def save_failed_queue(path: Path, queue: dict[str, Any]) -> None:
    atomic_write_json(path, queue)


def add_failed_item(
    queue: dict[str, Any],
    *,
    article_id: int | str | None,
    url: str | None,
    reason: str,
    failed_at: str,
) -> None:
    article_id_text = str(article_id) if article_id is not None else None
    items = queue.setdefault("items", [])
    for item in items:
        if str(item.get("article_id")) == article_id_text and item.get("url") == url:
            item["reason"] = reason
            item["retry_count"] = int(item.get("retry_count", 0)) + 1
            item["last_failed_at"] = failed_at
            return
    items.append(
        {
            "article_id": article_id_text,
            "url": url,
            "reason": reason,
            "retry_count": 1,
            "last_failed_at": failed_at,
        }
    )


def mock_articles() -> list[dict[str, Any]]:
    return [
        {
            "article_id": 900001,
            "url": "mock://naver-cafe/articles/900001",
            "title": "mock daily article 1",
            "author": "mock",
            "posted_at": "2026-05-28 08:00",
            "body": "dry-run body 1",
        },
        {
            "article_id": 900001,
            "url": "mock://naver-cafe/articles/900001",
            "title": "mock duplicate article",
            "author": "mock",
            "posted_at": "2026-05-28 08:00",
            "body": "duplicate body",
        },
        {
            "article_id": 900002,
            "url": "mock://naver-cafe/articles/900002",
            "title": "mock parse failure",
            "author": "mock",
            "posted_at": "2026-05-28 08:10",
            "simulate_failure": "parse_failed",
        },
        {
            "article_id": 900003,
            "url": "mock://naver-cafe/articles/900003",
            "title": "mock daily article 2",
            "author": "mock",
            "posted_at": "2026-05-28 08:20",
            "body": "dry-run body 2",
        },
    ]


def collect_new_articles(*, dry_run: bool) -> list[dict[str, Any]]:
    if dry_run:
        return mock_articles()
    raise RuntimeError("collect_new_articles only supports dry-run")


def collect_execute_articles(
    *,
    list_url: str | None,
    limit: int,
    page_limit: int | None,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    browser_profile_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Collect article list rows in execute mode with strict bounds.

    This is the single real-collection bridge. It reuses:
    - `BrowserSession` from `src/browser.py`
    - `parse_article_list` from `src/parser.py`

    If `list_url` is omitted, no browser is opened and no network request is sent.
    """
    if not list_url:
        return [], ["execute mode skipped: --list-url was not provided"]

    import time  # noqa: WPS433

    from browser import BrowserSession  # noqa: WPS433

    pages_to_scan = page_limit if page_limit is not None else DEFAULT_PAGE_LIMIT
    rows: list[dict[str, Any]] = []
    session = BrowserSession(user_data_dir=browser_profile_dir)
    try:
        for page_num in range(1, pages_to_scan + 1):
            page_rows, err = fetch_list_rows(session, list_url, page_num)
            if err:
                raise RuntimeError(f"list page {page_num} failed: {err}")
            for row in page_rows or []:
                rows.append(row)
                if len(rows) >= limit:
                    return rows, []
            if page_num < pages_to_scan:
                time.sleep(delay_seconds)
    finally:
        session.close()
    return rows, []


def fetch_list_rows(
    session: Any,
    list_url: str,
    page_num: int,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Fetch and parse one Cafe list page using the existing archive primitives."""
    from browser import check_blocked  # noqa: WPS433
    from parser import parse_article_list  # noqa: WPS433

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
    return parse_article_list(html, final_url), None


def build_page_url(base_url: str, page: int) -> str:
    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["page"] = [str(page)]
    new_query = urlencode({key: value[0] for key, value in qs.items()})
    return urlunparse(parsed._replace(query=new_query))


def collect_article_body(article_id: int) -> tuple[str, str | None]:
    from collector import collect_body  # noqa: WPS433

    return collect_body(article_id)


def is_duplicate(article_id: int, seen_ids: set[int], *, dry_run: bool) -> bool:
    if article_id in seen_ids:
        return True
    if dry_run:
        return False
    return article_exists(article_id)


def save_article(row: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        return
    upsert_article(
        Article(
            article_id=int(row["article_id"]),
            url=str(row["url"]),
            title=row.get("title"),
            author=row.get("author"),
            posted_at=row.get("posted_at"),
            raw_html=row.get("raw_html"),
            clean_text=row.get("body") or row.get("clean_text"),
            source_page=row.get("source_page"),
            status=Status.INDEXED,
        )
    )


def parse_row_article_id(row: dict[str, Any]) -> int:
    try:
        return int(row["article_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid article row: missing or invalid article_id") from exc


def run_daily_archive(
    *,
    dry_run: bool,
    execute: bool = False,
    limit: int = DEFAULT_LIMIT,
    page_limit: int | None = DEFAULT_PAGE_LIMIT,
    list_url: str | None = None,
    collect_body: bool = False,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    browser_profile_dir: Path | None = None,
    state_dir: Path = DEFAULT_STATE_DIR,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    today: datetime | None = None,
) -> tuple[DailyStats, Path]:
    run_at = today or now_kst()
    state_path = state_dir / ("crawl_state.dry-run.json" if dry_run else "crawl_state.json")
    failed_queue_path = state_dir / (
        "failed_queue.dry-run.json" if dry_run else "failed_queue.json"
    )

    state = load_crawl_state(state_path)
    failed_queue = load_failed_queue(failed_queue_path)
    stats = DailyStats(
        dry_run=dry_run,
        mode="dry-run" if dry_run else "execute",
        limit=limit,
        page_limit=page_limit,
    )
    seen_ids: set[int] = set()
    max_article: dict[str, Any] | None = None

    try:
        if dry_run:
            rows = collect_new_articles(dry_run=True)
        elif execute:
            rows, notes = collect_execute_articles(
                list_url=list_url,
                limit=limit,
                page_limit=page_limit,
                delay_seconds=delay_seconds,
                browser_profile_dir=browser_profile_dir,
            )
            stats.notes.extend(notes)
        else:
            rows = []
            stats.notes.append("no mode selected; use --dry-run or --execute")
    except Exception as exc:
        failed_at = run_at.isoformat()
        add_failed_item(
            failed_queue,
            article_id=None,
            url=list_url,
            reason=f"list_collection_failed: {exc}",
            failed_at=failed_at,
        )
        stats.failed += 1
        stats.failed_items.append(failed_queue["items"][-1])
        rows = []

    stats.discovered = min(len(rows), limit)
    if not dry_run and rows:
        init_db()

    for row in rows[:limit]:
        try:
            article_id = parse_row_article_id(row)
            if is_duplicate(article_id, seen_ids, dry_run=dry_run):
                stats.duplicates += 1
                continue

            seen_ids.add(article_id)
            if max_article is None or article_id > int(max_article["article_id"]):
                max_article = row

            if row.get("simulate_failure"):
                raise RuntimeError(str(row["simulate_failure"]))
            save_article(row, dry_run=dry_run)
            if collect_body and not dry_run:
                body_status, block_signal = collect_article_body(article_id)
                if body_status != Status.BODY_COLLECTED:
                    reason = f"body_collection_status={body_status}"
                    if block_signal:
                        reason += f", block_signal={block_signal}"
                    raise RuntimeError(reason)
            stats.saved += 1
        except Exception as exc:
            failed_at = run_at.isoformat()
            add_failed_item(
                failed_queue,
                article_id=row.get("article_id"),
                url=row.get("url"),
                reason=str(exc),
                failed_at=failed_at,
            )
            stats.failed += 1
            stats.failed_items.append(failed_queue["items"][-1])

    state["last_run_at"] = run_at.isoformat()
    state["total_runs"] = int(state.get("total_runs") or 0) + 1
    if max_article is not None:
        state["last_article_id"] = int(max_article["article_id"])
        state["last_article_url"] = max_article.get("url")
    if dry_run:
        stats.notes.append("dry-run: mock data only; data/archive.db was not modified.")
    else:
        stats.notes.append("execute: bounded archive collection path; DB duplicate checks enabled.")
        if not collect_body:
            stats.notes.append("body collection skipped; pass --collect-body to call collector.collect_body.")

    save_crawl_state(state_path, state)
    save_failed_queue(failed_queue_path, failed_queue)
    report_path = write_daily_report(reports_dir, run_at, stats)
    return stats, report_path


def prepare_manual_login(
    *,
    browser_profile_dir: Path | None = None,
    login_url: str = "https://nid.naver.com/nidlogin.login",
) -> int:
    from browser import BrowserSession, wait_for_login  # noqa: WPS433

    profile_dir = browser_profile_dir or DEFAULT_BROWSER_PROFILE_DIR
    print("[daily_archive] manual login mode")
    print(f"  browser_profile_dir: {profile_dir}")
    print("  no collection, DB write, state update, or report write will be performed")
    print("  complete Naver login manually in the opened browser")
    print("  do not attempt to bypass captcha or identity verification")

    session = BrowserSession(user_data_dir=profile_dir)
    try:
        _final_url, _err = session.goto(login_url)
        wait_for_login(session.page)
        print("[daily_archive] login preparation complete")
        return 0
    finally:
        session.close()


def write_daily_report(reports_dir: Path, run_at: datetime, stats: DailyStats) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    suffix = "-dry-run" if stats.dry_run else ""
    report_path = reports_dir / f"{run_at.date().isoformat()}{suffix}.md"
    failed_lines = [
        "- article_id={article_id} url={url} reason={reason} retry_count={retry_count}".format(
            article_id=item.get("article_id") or "-",
            url=item.get("url") or "-",
            reason=item.get("reason") or "-",
            retry_count=item.get("retry_count", 0),
        )
        for item in stats.failed_items
    ] or ["- none"]
    notes = stats.notes or ["No additional notes."]
    content = "\n".join(
        [
            f"# Daily Archive Report - {run_at.date().isoformat()}",
            "",
            "## Summary",
            f"- discovered: {stats.discovered}",
            f"- duplicates skipped: {stats.duplicates}",
            f"- saved: {stats.saved}",
            f"- failed: {stats.failed}",
            f"- mode: {stats.mode}",
            f"- dry-run: {'yes' if stats.dry_run else 'no'}",
            f"- limit: {stats.limit}",
            f"- page_limit: {stats.page_limit if stats.page_limit is not None else '-'}",
            "",
            "## Safety",
            f"- {mode_safety_message(stats)}",
            "",
            "## Failed Items",
            *failed_lines,
            "",
            "## Notes",
            *[f"- {note}" for note in notes],
            "",
        ]
    )
    report_path.write_text(content, encoding="utf-8")
    return report_path


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the daily archive pipeline")
    parser.add_argument("--dry-run", action="store_true", help="use mock data and avoid data/")
    parser.add_argument("--execute", action="store_true", help="run bounded archive collection")
    parser.add_argument("--login", action="store_true", help="open persistent browser profile for manual Naver login")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--page-limit", type=int, default=DEFAULT_PAGE_LIMIT)
    parser.add_argument("--list-url", default=None, help="Naver Cafe article-list URL for execute mode")
    parser.add_argument(
        "--collect-body",
        action="store_true",
        help="after indexing list rows, call collector.collect_body for saved articles",
    )
    parser.add_argument("--delay-seconds", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--browser-profile-dir", type=Path, default=DEFAULT_BROWSER_PROFILE_DIR)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    args = parser.parse_args(argv)
    selected_modes = sum(bool(flag) for flag in (args.dry_run, args.execute, args.login))
    if selected_modes > 1:
        parser.error("--dry-run, --execute, and --login are mutually exclusive")
    if args.execute and args.limit is None:
        parser.error("--execute requires --limit N")
    if args.execute and not args.list_url:
        parser.error("--execute requires --list-url <URL>")
    if args.limit is None:
        args.limit = DEFAULT_LIMIT
    if args.limit < 1 or args.limit > MAX_LIMIT:
        parser.error(f"--limit must be between 1 and {MAX_LIMIT}")
    if args.page_limit < 1 or args.page_limit > MAX_PAGE_LIMIT:
        parser.error(f"--page-limit must be between 1 and {MAX_PAGE_LIMIT}")
    if args.delay_seconds < 0:
        parser.error("--delay-seconds must be non-negative")
    return args


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.login:
        return prepare_manual_login(browser_profile_dir=args.browser_profile_dir)

    if not args.dry_run and not args.execute:
        print("[daily_archive] no collection mode selected")
        print("  no browser, network, DB, state, or report changes were made")
        print("  safe validation : python scripts/daily_archive.py --dry-run")
        print("  manual login    : python scripts/daily_archive.py --login")
        print("  real collection : python scripts/daily_archive.py --execute --limit N --list-url <URL>")
        print("  execute mode requires both --limit and --list-url and remains bounded")
        return 0

    try:
        stats, report_path = run_daily_archive(
            dry_run=args.dry_run,
            execute=args.execute,
            limit=args.limit,
            page_limit=args.page_limit,
            list_url=args.list_url,
            collect_body=args.collect_body,
            delay_seconds=args.delay_seconds,
            browser_profile_dir=args.browser_profile_dir,
            state_dir=args.state_dir,
            reports_dir=args.reports_dir,
        )
    except Exception as exc:
        print(f"[daily_archive] ERROR: {exc}", file=sys.stderr)
        return 1

    print("[daily_archive] done")
    print(f"  mode       : {stats.mode}")
    print(f"  dry_run    : {stats.dry_run}")
    print(f"  limit      : {stats.limit}")
    print(f"  page_limit : {stats.page_limit}")
    print(f"  discovered : {stats.discovered}")
    print(f"  duplicates : {stats.duplicates}")
    print(f"  saved      : {stats.saved}")
    print(f"  failed     : {stats.failed}")
    print(f"  report     : {report_path}")
    print(f"  safety     : {mode_safety_message(stats)}")
    if stats.notes:
        print("  notes      :")
        for note in stats.notes:
            print(f"    - {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
