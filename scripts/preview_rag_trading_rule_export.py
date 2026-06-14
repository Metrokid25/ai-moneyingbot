from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_FILE = PROJECT_ROOT / "agent_reports" / "rag_rule_candidate_registry.jsonl"
DEFAULT_OUT_DIR = PROJECT_ROOT / "agent_reports"
EXPORT_PREVIEW_STATUS = "preview_needs_human_review"
DEFAULT_STATUS_FILTER = "registered_needs_final_review"
DB_ONLY_NOTICE = (
    "DB-only RAG trading export preview: use only the RAG-internal rule "
    "candidate registry and the DB-grounded fields already present in it. Do "
    "not use external web search, current market news, general economic "
    "knowledge, Naver Cafe access, archive writes, or archive.db/data mutations."
)
TRADING_BOT_NO_AUTO_APPLY_NOTICE = (
    "Trading Bot automatic application is prohibited: this preview must not "
    "create, export, or modify Trading Bot rules or Trading Bot files."
)
PREVIEW_NOT_EXPORT_NOTICE = (
    "This report is a human review preview, not a Trading Bot input file, not "
    "a rule export, and not a trading signal."
)


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def timestamp_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def normalize_space(value: Any) -> str:
    return " ".join(str(value or "").replace("\u200b", " ").split())


def coerce_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


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


def category_matches(row: dict[str, Any], category_filters: Sequence[str]) -> bool:
    filters = {normalize_space(category) for category in category_filters if normalize_space(category)}
    if not filters:
        return True
    return normalize_space(row.get("rule_candidate_category")) in filters


def candidate_from_registry_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    preview_id = f"rag_trading_export_preview_{index:04d}"
    source_boundary = normalize_space(row.get("boundary_notice"))
    boundary_notice = " ".join(
        part
        for part in (
            source_boundary,
            TRADING_BOT_NO_AUTO_APPLY_NOTICE,
            PREVIEW_NOT_EXPORT_NOTICE,
        )
        if part
    )
    return {
        "preview_id": preview_id,
        "registry_id": normalize_space(row.get("registry_id")),
        "source_rule_candidate_id": normalize_space(row.get("source_rule_candidate_id")),
        "rule_candidate_category": normalize_space(row.get("rule_candidate_category")),
        "registry_status": normalize_space(row.get("registry_status")),
        "export_preview_status": EXPORT_PREVIEW_STATUS,
        "rule_candidate_summary": normalize_space(row.get("rule_candidate_summary")),
        "source_question": normalize_space(row.get("source_question")),
        "source_answer": normalize_space(row.get("source_answer")),
        "evidence_strength": normalize_space(row.get("evidence_strength")),
        "source_refs": coerce_list(row.get("source_refs")),
        "used_sources": coerce_list(row.get("used_sources")),
        "tags": coerce_list(row.get("tags")),
        "schema_name": normalize_space(row.get("schema_name")),
        "schema_version": row.get("schema_version"),
        "boundary_notice": boundary_notice,
        "trading_export_preview_note": (
            "Human review required. This is a preview-only record and not a "
            "trading signal or Trading Bot input file."
        ),
    }


def select_preview_candidates(
    rows: Sequence[dict[str, Any]],
    *,
    status_filter: str,
    category_filters: Sequence[str],
    limit: int | None,
) -> tuple[list[dict[str, Any]], int, int]:
    candidates: list[dict[str, Any]] = []
    skipped_status_count = 0
    skipped_category_count = 0
    normalized_status = normalize_space(status_filter)
    for row in rows:
        if limit is not None and len(candidates) >= limit:
            break
        if normalize_space(row.get("registry_status")) != normalized_status:
            skipped_status_count += 1
            continue
        if not category_matches(row, category_filters):
            skipped_category_count += 1
            continue
        candidates.append(candidate_from_registry_row(row, len(candidates) + 1))
    return candidates, skipped_status_count, skipped_category_count


def build_summary(
    *,
    registry_file: Path,
    candidates: Sequence[dict[str, Any]],
    skipped_status_count: int,
    skipped_category_count: int,
    dry_run: bool,
    generated_at: str,
    status_filter: str,
    category_filters: Sequence[str],
) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "registry_file": str(registry_file),
        "preview_count": len(candidates),
        "skipped_status_count": skipped_status_count,
        "skipped_category_count": skipped_category_count,
        "dry_run": dry_run,
        "status_filter": status_filter,
        "category_filters": [category for category in category_filters],
        "db_only_notice": DB_ONLY_NOTICE,
        "trading_boundary_notice": TRADING_BOT_NO_AUTO_APPLY_NOTICE,
        "preview_not_export_notice": PREVIEW_NOT_EXPORT_NOTICE,
        "candidates": list(candidates),
    }


def format_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# RAG Trading Rule Export Preview",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- registry_file: {summary['registry_file']}",
        f"- preview_count: {summary['preview_count']}",
        f"- skipped_status_count: {summary['skipped_status_count']}",
        f"- skipped_category_count: {summary['skipped_category_count']}",
        f"- dry_run: {str(summary['dry_run']).lower()}",
        f"- status_filter: {summary['status_filter']}",
        f"- category_filters: {json.dumps(summary['category_filters'], ensure_ascii=True)}",
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
        summary["preview_not_export_notice"],
        "",
        "## Preview Candidates",
        "",
    ]
    if not summary["candidates"]:
        lines.append("- none")
        return "\n".join(lines).rstrip() + "\n"

    for index, candidate in enumerate(summary["candidates"], start=1):
        lines.extend(
            [
                f"### {index}. {candidate['preview_id']}",
                "",
                f"- registry_id: {candidate['registry_id']}",
                f"- source_rule_candidate_id: {candidate['source_rule_candidate_id']}",
                f"- rule_candidate_category: {candidate['rule_candidate_category']}",
                f"- registry_status: {candidate['registry_status']}",
                f"- export_preview_status: {candidate['export_preview_status']}",
                f"- evidence_strength: {candidate['evidence_strength']}",
                f"- source_refs: {json.dumps(candidate['source_refs'], ensure_ascii=True)}",
                f"- used_sources: {json.dumps(candidate['used_sources'], ensure_ascii=True)}",
                f"- tags: {json.dumps(candidate['tags'], ensure_ascii=True)}",
                f"- schema_name: {candidate['schema_name']}",
                f"- schema_version: {candidate['schema_version']}",
                f"- trading_export_preview_note: {candidate['trading_export_preview_note']}",
                "",
                "Summary:",
                "",
                candidate["rule_candidate_summary"] or "(empty)",
                "",
                "Source Question:",
                "",
                candidate["source_question"] or "(empty)",
                "",
                "Source Answer:",
                "",
                candidate["source_answer"] or "(empty)",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_reports(out_dir: Path, stamp: str, summary: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"rag-trading-rule-export-preview-{stamp}.json"
    md_path = out_dir / f"rag-trading-rule-export-preview-{stamp}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_markdown_report(summary), encoding="utf-8", newline="\n")
    return json_path, md_path


def preview_export(
    *,
    registry_file: Path | None = None,
    out_dir: Path = DEFAULT_OUT_DIR,
    limit: int | None = None,
    category_filters: Sequence[str] = (),
    status_filter: str = DEFAULT_STATUS_FILTER,
    dry_run: bool = False,
    timestamp: str | None = None,
) -> tuple[dict[str, Any], Path | None, Path | None]:
    if limit is not None and limit < 0:
        raise ValueError("--limit must be zero or greater")
    stamp = timestamp or timestamp_now()
    resolved_registry = registry_file or DEFAULT_REGISTRY_FILE
    rows = read_jsonl(resolved_registry)
    candidates, skipped_status_count, skipped_category_count = select_preview_candidates(
        rows,
        status_filter=status_filter,
        category_filters=category_filters,
        limit=limit,
    )
    summary = build_summary(
        registry_file=resolved_registry,
        candidates=candidates,
        skipped_status_count=skipped_status_count,
        skipped_category_count=skipped_category_count,
        dry_run=dry_run,
        generated_at=stamp,
        status_filter=status_filter,
        category_filters=category_filters,
    )
    if dry_run:
        return summary, None, None
    json_path, md_path = write_reports(out_dir, stamp, summary)
    return summary, json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview RAG registry candidates for later human Trading Bot handoff review.",
        epilog=f"{DB_ONLY_NOTICE} {TRADING_BOT_NO_AUTO_APPLY_NOTICE} {PREVIEW_NOT_EXPORT_NOTICE}",
    )
    parser.add_argument("--registry-file", type=Path, default=DEFAULT_REGISTRY_FILE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--category-filter", action="append", default=[])
    parser.add_argument("--status-filter", default=DEFAULT_STATUS_FILTER)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    try:
        summary, json_path, md_path = preview_export(
            registry_file=args.registry_file,
            out_dir=args.out_dir,
            limit=args.limit,
            category_filters=args.category_filter,
            status_filter=args.status_filter,
            dry_run=args.dry_run,
            timestamp=args.timestamp,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(DB_ONLY_NOTICE)
    print(TRADING_BOT_NO_AUTO_APPLY_NOTICE)
    print(PREVIEW_NOT_EXPORT_NOTICE)
    print(f"Preview candidates: {summary['preview_count']}")
    print(f"Skipped status: {summary['skipped_status_count']}")
    print(f"Skipped category: {summary['skipped_category_count']}")
    if args.dry_run:
        print("Dry run: no trading export preview report files written.")
    else:
        print(f"JSON: {json_path}")
        print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
