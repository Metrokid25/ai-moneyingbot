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
ALLOWED_EXPORT_CATEGORIES = {"principle", "pattern", "risk_control", "watch_condition", "unresolved"}
DB_ONLY_NOTICE = (
    "DB-only approved memory export preview: use only internal DB retrieval outputs, "
    "agent reports, fixtures, docs, and the RAG research memory store. Do not use "
    "external web search, current market news, general economic knowledge, Naver Cafe "
    "access, archive writes, or archive.db/data mutations."
)
NO_TRADING_BOT_AUTO_APPLY_NOTICE = (
    "Trading Bot automatic application is prohibited: this preview must not create, "
    "export, or modify Trading Bot rules or Trading Bot files."
)
PREVIEW_ONLY_NOTICE = (
    "This file is an export preview, not a rule export. Approved memory is not a "
    "confirmed trading rule and still requires human review before any later rule "
    "candidate conversion."
)


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


def promotion_review_status(record: dict[str, Any]) -> str:
    review = record.get("promotion_review")
    if isinstance(review, dict):
        return normalize_space(review.get("status"))
    return ""


def is_approved_record(record: dict[str, Any]) -> bool:
    return normalize_space(record.get("promotion_status")) == "approved" or promotion_review_status(record) == "approved"


def tags_match(record: dict[str, Any], tag_filters: Sequence[str]) -> bool:
    filters = {normalize_space(tag).lower() for tag in tag_filters if normalize_space(tag)}
    if not filters:
        return True
    tags = {normalize_space(tag).lower() for tag in coerce_list(record.get("tags")) if normalize_space(tag)}
    return bool(tags & filters)


def joined_record_text(record: dict[str, Any]) -> str:
    parts = [
        record.get("question"),
        record.get("answer"),
        record.get("evidence_strength"),
        " ".join(str(tag) for tag in coerce_list(record.get("tags"))),
    ]
    return normalize_space(" ".join(str(part or "") for part in parts)).lower()


def suggest_export_category(record: dict[str, Any]) -> str:
    text = joined_record_text(record)
    if any(keyword in text for keyword in ("risk", "loss", "stop", "position size", "exposure", "drawdown")):
        return "risk_control"
    if any(keyword in text for keyword in ("watch", "monitor", "condition", "trigger", "signal", "threshold")):
        return "watch_condition"
    if any(keyword in text for keyword in ("pattern", "repeat", "tends", "when ", "after ")):
        return "pattern"
    if any(keyword in text for keyword in ("principle", "always", "avoid", "prefer", "should")):
        return "principle"
    return "unresolved"


def suggest_rule_candidate_summary(record: dict[str, Any]) -> str:
    question = normalize_space(record.get("question"))
    answer = normalize_space(record.get("answer"))
    base_text = answer or question
    if not base_text:
        return "No internal memory text was available for a reviewer-facing summary."
    if len(base_text) <= 240:
        return base_text
    return base_text[:237].rstrip() + "..."


def candidate_from_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_id": normalize_space(record.get("memory_id")),
        "question_id": normalize_space(record.get("question_id")),
        "question": normalize_space(record.get("question")),
        "answer": normalize_space(record.get("answer")),
        "evidence_strength": normalize_space(record.get("evidence_strength")),
        "source_refs": coerce_list(record.get("source_refs")),
        "used_sources": coerce_list(record.get("used_sources")),
        "tags": coerce_list(record.get("tags")),
        "promotion_status": normalize_space(record.get("promotion_status")),
        "promotion_review": record.get("promotion_review") if isinstance(record.get("promotion_review"), dict) else {},
        "suggested_export_category": suggest_export_category(record),
        "suggested_rule_candidate_summary": suggest_rule_candidate_summary(record),
    }


def select_candidates(
    records: Sequence[dict[str, Any]],
    *,
    limit: int | None,
    tag_filters: Sequence[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for record in records:
        if limit is not None and len(candidates) >= limit:
            break
        if not is_approved_record(record):
            continue
        if not tags_match(record, tag_filters):
            continue
        candidates.append(candidate_from_record(record))
    return candidates


def build_preview_summary(
    *,
    memory_store_file: Path,
    candidates: Sequence[dict[str, Any]],
    dry_run: bool,
    generated_at: str,
    tag_filters: Sequence[str],
) -> dict[str, Any]:
    return {
        "memory_store_file": str(memory_store_file),
        "generated_at": generated_at,
        "approved_count": len(candidates),
        "dry_run": dry_run,
        "tag_filters": [tag for tag in tag_filters],
        "db_only_notice": DB_ONLY_NOTICE,
        "trading_boundary_notice": NO_TRADING_BOT_AUTO_APPLY_NOTICE,
        "preview_only_notice": PREVIEW_ONLY_NOTICE,
        "allowed_suggested_export_categories": sorted(ALLOWED_EXPORT_CATEGORIES),
        "candidates": list(candidates),
    }


def format_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# RAG Approved Memory Export Preview",
        "",
        f"- memory_store_file: {summary['memory_store_file']}",
        f"- generated_at: {summary['generated_at']}",
        f"- approved_count: {summary['approved_count']}",
        f"- dry_run: {str(summary['dry_run']).lower()}",
        f"- tag_filters: {json.dumps(summary['tag_filters'], ensure_ascii=True)}",
        "",
        "## DB-only Boundary",
        "",
        summary["db_only_notice"],
        "",
        "## Trading Bot Boundary",
        "",
        summary["trading_boundary_notice"],
        "",
        "## Preview Boundary",
        "",
        summary["preview_only_notice"],
        "",
        "## Approved Candidates",
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
                f"- memory_id: {candidate['memory_id']}",
                f"- question_id: {candidate['question_id']}",
                f"- question: {candidate['question']}",
                f"- evidence_strength: {candidate['evidence_strength']}",
                f"- source_refs: {json.dumps(candidate['source_refs'], ensure_ascii=True)}",
                f"- used_sources: {json.dumps(candidate['used_sources'], ensure_ascii=True)}",
                f"- tags: {json.dumps(candidate['tags'], ensure_ascii=True)}",
                f"- promotion_status: {candidate['promotion_status']}",
                f"- promotion_review: {json.dumps(candidate['promotion_review'], ensure_ascii=True, sort_keys=True)}",
                f"- suggested_export_category: {candidate['suggested_export_category']}",
                f"- suggested_rule_candidate_summary: {candidate['suggested_rule_candidate_summary']}",
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
    json_path = out_dir / f"rag-approved-memory-export-preview-{stamp}.json"
    md_path = out_dir / f"rag-approved-memory-export-preview-{stamp}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_markdown_report(summary), encoding="utf-8", newline="\n")
    return json_path, md_path


def preview_export(
    *,
    memory_store_file: Path = DEFAULT_MEMORY_STORE,
    out_dir: Path = DEFAULT_OUT_DIR,
    limit: int | None = None,
    tag_filters: Sequence[str] = (),
    dry_run: bool = False,
    timestamp: str | None = None,
) -> tuple[dict[str, Any], Path | None, Path | None]:
    if limit is not None and limit < 0:
        raise ValueError("--limit must be zero or greater")
    stamp = timestamp or timestamp_now()
    records = read_jsonl(memory_store_file)
    candidates = select_candidates(records, limit=limit, tag_filters=tag_filters)
    summary = build_preview_summary(
        memory_store_file=memory_store_file,
        candidates=candidates,
        dry_run=dry_run,
        generated_at=stamp,
        tag_filters=tag_filters,
    )
    if dry_run:
        return summary, None, None
    json_path, md_path = write_reports(out_dir, stamp, summary)
    return summary, json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview approved RAG research memory records for later human rule-candidate review.",
        epilog=f"{DB_ONLY_NOTICE} {NO_TRADING_BOT_AUTO_APPLY_NOTICE} {PREVIEW_ONLY_NOTICE}",
    )
    parser.add_argument("--memory-store-file", type=Path, default=DEFAULT_MEMORY_STORE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--tag-filter", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    try:
        summary, json_path, md_path = preview_export(
            memory_store_file=args.memory_store_file,
            out_dir=args.out_dir,
            limit=args.limit,
            tag_filters=args.tag_filter,
            dry_run=args.dry_run,
            timestamp=args.timestamp,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(DB_ONLY_NOTICE)
    print(NO_TRADING_BOT_AUTO_APPLY_NOTICE)
    print(PREVIEW_ONLY_NOTICE)
    print(f"Approved candidates: {summary['approved_count']}")
    if args.dry_run:
        print("Dry run: no export preview report files written.")
    else:
        print(f"JSON: {json_path}")
        print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
