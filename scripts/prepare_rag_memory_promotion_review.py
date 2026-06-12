from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MEMORY_STORE = PROJECT_ROOT / "agent_reports" / "rag_research_memory_store.jsonl"
DEFAULT_OUT_DIR = PROJECT_ROOT / "agent_reports"
DB_ONLY_NOTICE = (
    "DB-only promotion review: use only internal DB retrieval outputs, "
    "agent reports, fixtures, docs, and the RAG research memory store. Do not "
    "use external web search, current market news, general economic knowledge, "
    "Naver Cafe access, archive writes, or archive.db/data mutations."
)
NO_TRADING_BOT_NOTICE = (
    "Approved memory records must not be automatically exported to Trading Bot "
    "rules or used to create or modify Trading Bot files."
)
DEFAULT_PENDING_STATUSES = {"", "pending", "pending_human_review"}
REVIEW_ACTIONS = "approve / reject / keep_pending"


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def timestamp_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def normalize_space(value: Any) -> str:
    return " ".join(str(value or "").replace("\u200b", " ").split())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for line_no, line in enumerate(fh, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: row must be a JSON object")
            rows.append(row)
    return rows


def coerce_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def status_matches(record: dict[str, Any], status_filter: str | None) -> bool:
    status = normalize_space(record.get("promotion_status"))
    if status_filter is None:
        return status in DEFAULT_PENDING_STATUSES
    return status == normalize_space(status_filter)


def candidate_from_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_id": normalize_space(record.get("memory_id")),
        "question": normalize_space(record.get("question")),
        "answer_status": normalize_space(record.get("answer_status")),
        "evidence_strength": normalize_space(record.get("evidence_strength")),
        "answer": normalize_space(record.get("answer")),
        "source_refs": coerce_list(record.get("source_refs")),
        "used_sources": coerce_list(record.get("used_sources")),
        "tags": coerce_list(record.get("tags")),
        "promotion_status": normalize_space(record.get("promotion_status")),
        "recommended_reviewer_action": REVIEW_ACTIONS,
    }


def select_candidates(
    records: Sequence[dict[str, Any]],
    *,
    status_filter: str | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for record in records:
        if not status_matches(record, status_filter):
            continue
        candidates.append(candidate_from_record(record))
        if limit is not None and len(candidates) >= limit:
            break
    return candidates


def build_review_summary(
    *,
    memory_store_file: Path,
    candidates: Sequence[dict[str, Any]],
    dry_run: bool,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "memory_store_file": str(memory_store_file),
        "generated_at": generated_at,
        "candidate_count": len(candidates),
        "dry_run": dry_run,
        "db_only_notice": DB_ONLY_NOTICE,
        "no_rule_export_notice": NO_TRADING_BOT_NOTICE,
        "candidates": list(candidates),
    }


def format_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# RAG Memory Promotion Review",
        "",
        f"- memory_store_file: {summary['memory_store_file']}",
        f"- generated_at: {summary['generated_at']}",
        f"- candidate_count: {summary['candidate_count']}",
        f"- dry_run: {str(summary['dry_run']).lower()}",
        "",
        "## DB-only Safety",
        "",
        summary["db_only_notice"],
        "",
        "## Trading Bot Boundary",
        "",
        summary["no_rule_export_notice"],
        "",
        "## Candidates",
        "",
    ]
    if not summary["candidates"]:
        lines.append("- none")
        return "\n".join(lines).rstrip() + "\n"

    for index, candidate in enumerate(summary["candidates"], start=1):
        lines.extend(
            [
                f"### {index}. {candidate['memory_id'] or 'missing-memory-id'}",
                "",
                f"- question: {candidate['question']}",
                f"- answer_status: {candidate['answer_status']}",
                f"- evidence_strength: {candidate['evidence_strength']}",
                f"- promotion_status: {candidate['promotion_status']}",
                f"- recommended reviewer action: {candidate['recommended_reviewer_action']}",
                f"- source_refs: {json.dumps(candidate['source_refs'], ensure_ascii=True)}",
                f"- used_sources: {json.dumps(candidate['used_sources'], ensure_ascii=True)}",
                f"- tags: {json.dumps(candidate['tags'], ensure_ascii=True)}",
                "",
                "Answer:",
                "",
                candidate["answer"] or "(empty)",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_reports(out_dir: Path, stamp: str, summary: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"rag-memory-promotion-review-{stamp}.json"
    md_path = out_dir / f"rag-memory-promotion-review-{stamp}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_markdown_report(summary), encoding="utf-8", newline="\n")
    return json_path, md_path


def prepare_review(
    *,
    memory_store_file: Path = DEFAULT_MEMORY_STORE,
    out_dir: Path = DEFAULT_OUT_DIR,
    limit: int | None = None,
    status_filter: str | None = None,
    dry_run: bool = False,
    timestamp: str | None = None,
) -> tuple[dict[str, Any], Path | None, Path | None]:
    if limit is not None and limit < 0:
        raise ValueError("--limit must be zero or greater")
    stamp = timestamp or timestamp_now()
    records = read_jsonl(memory_store_file)
    candidates = select_candidates(records, status_filter=status_filter, limit=limit)
    summary = build_review_summary(
        memory_store_file=memory_store_file,
        candidates=candidates,
        dry_run=dry_run,
        generated_at=stamp,
    )
    if dry_run:
        return summary, None, None
    json_path, md_path = write_reports(out_dir, stamp, summary)
    return summary, json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a human review report for pending RAG research memory promotion candidates.",
        epilog=f"{DB_ONLY_NOTICE} {NO_TRADING_BOT_NOTICE}",
    )
    parser.add_argument("--memory-store-file", type=Path, default=DEFAULT_MEMORY_STORE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--status-filter", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    try:
        summary, json_path, md_path = prepare_review(
            memory_store_file=args.memory_store_file,
            out_dir=args.out_dir,
            limit=args.limit,
            status_filter=args.status_filter,
            dry_run=args.dry_run,
            timestamp=args.timestamp,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(DB_ONLY_NOTICE)
    print(NO_TRADING_BOT_NOTICE)
    print(f"Candidates: {summary['candidate_count']}")
    if args.dry_run:
        print("Dry run: no review report files written.")
    else:
        print(f"JSON: {json_path}")
        print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
