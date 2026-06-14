from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "agent_reports"
PREVIEW_GLOB = "rag-approved-memory-export-preview-*.json"
SCHEMA_NAME = "rag_rule_candidate_draft"
SCHEMA_VERSION = 1
ALLOWED_CATEGORIES = {"principle", "pattern", "risk_control", "watch_condition", "unresolved"}
ALLOWED_DRAFT_STATUSES = {"draft_needs_human_review", "rejected", "approved_for_registry"}
DB_ONLY_NOTICE = (
    "DB-only RAG rule candidate draft: use only internal approved memory export "
    "preview reports and the DB-grounded memory text already present in those reports. "
    "Do not use external web search, current market news, general economic knowledge, "
    "Naver Cafe access, archive writes, or archive.db/data mutations."
)
TRADING_BOUNDARY_NOTICE = (
    "Trading Bot integration is prohibited: this draft must not create, export, "
    "or modify Trading Bot rules or Trading Bot files."
)
DRAFT_ONLY_NOTICE = (
    "This file is a RAG-internal rule candidate draft report, not a rule export. "
    "Draft candidates are not confirmed trading rules and require later human review."
)
DRAFT_STATUS = "draft_needs_human_review"


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


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: report must be a JSON object")
    return value


def latest_preview_file(reports_dir: Path = DEFAULT_REPORTS_DIR) -> Path:
    matches = sorted(reports_dir.glob(PREVIEW_GLOB))
    if not matches:
        raise FileNotFoundError(f"no approved memory export preview report found in {reports_dir}")
    return matches[-1]


def tags_match(candidate: dict[str, Any], tag_filters: Sequence[str]) -> bool:
    filters = {normalize_space(tag).lower() for tag in tag_filters if normalize_space(tag)}
    if not filters:
        return True
    tags = {normalize_space(tag).lower() for tag in coerce_list(candidate.get("tags")) if normalize_space(tag)}
    return bool(tags & filters)


def category_matches(candidate: dict[str, Any], category_filters: Sequence[str]) -> bool:
    filters = {normalize_space(category) for category in category_filters if normalize_space(category)}
    if not filters:
        return True
    unknown = filters - ALLOWED_CATEGORIES
    if unknown:
        raise ValueError(f"--category-filter must be one of: {', '.join(sorted(ALLOWED_CATEGORIES))}")
    return normalize_space(candidate.get("suggested_export_category")) in filters


def draft_summary(candidate: dict[str, Any]) -> str:
    summary = normalize_space(candidate.get("suggested_rule_candidate_summary"))
    answer = normalize_space(candidate.get("answer"))
    question = normalize_space(candidate.get("question"))
    base_text = summary or answer or question
    if not base_text:
        return "No preview text was available for a reviewer-facing draft summary."
    if len(base_text) <= 260:
        return base_text
    return base_text[:257].rstrip() + "..."


def draft_review_note(candidate: dict[str, Any]) -> str:
    category = normalize_space(candidate.get("suggested_export_category")) or "unresolved"
    memory_id = normalize_space(candidate.get("memory_id")) or "missing-memory-id"
    return (
        f"Human review required before any rule conversion. Source memory {memory_id} "
        f"was grouped as {category} by the approved memory export preview."
    )


def draft_from_preview_candidate(candidate: dict[str, Any], index: int) -> dict[str, Any]:
    category = normalize_space(candidate.get("suggested_export_category")) or "unresolved"
    if category not in ALLOWED_CATEGORIES:
        category = "unresolved"
    memory_id = normalize_space(candidate.get("memory_id"))
    draft_id = f"rag_rule_candidate_draft_{index:04d}"
    return {
        "candidate_id": draft_id,
        "rule_candidate_id": draft_id,
        "draft_id": draft_id,
        "draft_status": DRAFT_STATUS,
        "source_memory_id": memory_id,
        "question_id": normalize_space(candidate.get("question_id")),
        "source_question": normalize_space(candidate.get("question")),
        "question": normalize_space(candidate.get("question")),
        "source_answer": normalize_space(candidate.get("answer")),
        "answer": normalize_space(candidate.get("answer")),
        "evidence_strength": normalize_space(candidate.get("evidence_strength")),
        "source_refs": coerce_list(candidate.get("source_refs")),
        "used_sources": coerce_list(candidate.get("used_sources")),
        "tags": coerce_list(candidate.get("tags")),
        "source_promotion_status": normalize_space(candidate.get("promotion_status")),
        "source_promotion_review": candidate.get("promotion_review")
        if isinstance(candidate.get("promotion_review"), dict)
        else {},
        "rule_candidate_category": category,
        "suggested_export_category": category,
        "rule_candidate_summary": draft_summary(candidate),
        "draft_summary": draft_summary(candidate),
        "draft_rule_candidate_summary": draft_summary(candidate),
        "draft_review_note": draft_review_note(candidate),
        "boundary_notice": f"{TRADING_BOUNDARY_NOTICE} {DRAFT_ONLY_NOTICE}",
        "draft_only_notice": DRAFT_ONLY_NOTICE,
    }


def select_draft_candidates(
    preview_candidates: Sequence[dict[str, Any]],
    *,
    limit: int | None,
    tag_filters: Sequence[str],
    category_filters: Sequence[str],
) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    for candidate in preview_candidates:
        if limit is not None and len(drafts) >= limit:
            break
        if not isinstance(candidate, dict):
            continue
        if not tags_match(candidate, tag_filters):
            continue
        if not category_matches(candidate, category_filters):
            continue
        drafts.append(draft_from_preview_candidate(candidate, len(drafts) + 1))
    return drafts


def build_draft_report(
    *,
    preview_file: Path,
    preview_report: dict[str, Any],
    drafts: Sequence[dict[str, Any]],
    dry_run: bool,
    generated_at: str,
    tag_filters: Sequence[str],
    category_filters: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "preview_file": str(preview_file),
        "source_memory_store_file": normalize_space(preview_report.get("memory_store_file")),
        "source_preview_generated_at": normalize_space(preview_report.get("generated_at")),
        "generated_at": generated_at,
        "candidate_count": len(drafts),
        "draft_count": len(drafts),
        "dry_run": dry_run,
        "tag_filters": [tag for tag in tag_filters],
        "category_filters": [category for category in category_filters],
        "db_only_notice": DB_ONLY_NOTICE,
        "trading_boundary_notice": TRADING_BOUNDARY_NOTICE,
        "draft_only_notice": DRAFT_ONLY_NOTICE,
        "allowed_categories": sorted(ALLOWED_CATEGORIES),
        "allowed_draft_statuses": sorted(ALLOWED_DRAFT_STATUSES),
        "candidates": list(drafts),
        "draft_candidates": list(drafts),
    }


def format_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# RAG Approved Memory Rule Candidate Draft",
        "",
        f"- schema_name: {report['schema_name']}",
        f"- schema_version: {report['schema_version']}",
        f"- preview_file: {report['preview_file']}",
        f"- source_memory_store_file: {report['source_memory_store_file']}",
        f"- source_preview_generated_at: {report['source_preview_generated_at']}",
        f"- generated_at: {report['generated_at']}",
        f"- draft_count: {report['draft_count']}",
        f"- dry_run: {str(report['dry_run']).lower()}",
        f"- tag_filters: {json.dumps(report['tag_filters'], ensure_ascii=True)}",
        f"- category_filters: {json.dumps(report['category_filters'], ensure_ascii=True)}",
        "",
        "## DB-only Boundary",
        "",
        report["db_only_notice"],
        "",
        "## Trading Bot Boundary",
        "",
        report["trading_boundary_notice"],
        "",
        "## Draft Boundary",
        "",
        report["draft_only_notice"],
        "",
        "## Draft Candidates",
        "",
    ]
    if not report["draft_candidates"]:
        lines.append("- none")
        return "\n".join(lines).rstrip() + "\n"

    for index, draft in enumerate(report["draft_candidates"], start=1):
        lines.extend(
            [
                f"### {index}. {draft['draft_id']}",
                "",
                f"- candidate_id: {draft['candidate_id']}",
                f"- draft_status: {draft['draft_status']}",
                f"- source_memory_id: {draft['source_memory_id']}",
                f"- question_id: {draft['question_id']}",
                f"- evidence_strength: {draft['evidence_strength']}",
                f"- source_refs: {json.dumps(draft['source_refs'], ensure_ascii=True)}",
                f"- used_sources: {json.dumps(draft['used_sources'], ensure_ascii=True)}",
                f"- tags: {json.dumps(draft['tags'], ensure_ascii=True)}",
                f"- source_promotion_status: {draft['source_promotion_status']}",
                f"- source_promotion_review: {json.dumps(draft['source_promotion_review'], ensure_ascii=True, sort_keys=True)}",
                f"- suggested_export_category: {draft['suggested_export_category']}",
                f"- draft_rule_candidate_summary: {draft['draft_rule_candidate_summary']}",
                f"- draft_review_note: {draft['draft_review_note']}",
                "",
                "Question:",
                "",
                draft["question"] or "(empty)",
                "",
                "Answer:",
                "",
                draft["answer"] or "(empty)",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_reports(out_dir: Path, stamp: str, report: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"rag-approved-memory-rule-candidate-draft-{stamp}.json"
    md_path = out_dir / f"rag-approved-memory-rule-candidate-draft-{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_markdown_report(report), encoding="utf-8", newline="\n")
    return json_path, md_path


def draft_rule_candidates(
    *,
    preview_file: Path | None = None,
    out_dir: Path = DEFAULT_REPORTS_DIR,
    limit: int | None = None,
    tag_filters: Sequence[str] = (),
    category_filters: Sequence[str] = (),
    dry_run: bool = False,
    timestamp: str | None = None,
) -> tuple[dict[str, Any], Path | None, Path | None]:
    if limit is not None and limit < 0:
        raise ValueError("--limit must be zero or greater")
    resolved_preview = preview_file or latest_preview_file(DEFAULT_REPORTS_DIR)
    preview_report = read_json_object(resolved_preview)
    preview_candidates = preview_report.get("candidates")
    if not isinstance(preview_candidates, list):
        raise ValueError(f"{resolved_preview}: missing candidates list")

    drafts = select_draft_candidates(
        preview_candidates,
        limit=limit,
        tag_filters=tag_filters,
        category_filters=category_filters,
    )
    stamp = timestamp or timestamp_now()
    report = build_draft_report(
        preview_file=resolved_preview,
        preview_report=preview_report,
        drafts=drafts,
        dry_run=dry_run,
        generated_at=stamp,
        tag_filters=tag_filters,
        category_filters=category_filters,
    )
    if dry_run:
        return report, None, None
    json_path, md_path = write_reports(out_dir, stamp, report)
    return report, json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Draft RAG-internal rule candidate review reports from approved memory export previews.",
        epilog=f"{DB_ONLY_NOTICE} {TRADING_BOUNDARY_NOTICE} {DRAFT_ONLY_NOTICE}",
    )
    parser.add_argument("--preview-file", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--tag-filter", action="append", default=[])
    parser.add_argument("--category-filter", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    try:
        report, json_path, md_path = draft_rule_candidates(
            preview_file=args.preview_file,
            out_dir=args.out_dir,
            limit=args.limit,
            tag_filters=args.tag_filter,
            category_filters=args.category_filter,
            dry_run=args.dry_run,
            timestamp=args.timestamp,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(DB_ONLY_NOTICE)
    print(TRADING_BOUNDARY_NOTICE)
    print(DRAFT_ONLY_NOTICE)
    print(f"Draft candidates: {report['draft_count']}")
    if args.dry_run:
        print("Dry run: no rule candidate draft report files written.")
    else:
        print(f"JSON: {json_path}")
        print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
