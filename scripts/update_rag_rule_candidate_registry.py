from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import validate_rag_rule_candidate_drafts as draft_schema


DEFAULT_REPORTS_DIR = PROJECT_ROOT / "agent_reports"
DEFAULT_REGISTRY_FILE = DEFAULT_REPORTS_DIR / "rag_rule_candidate_registry.jsonl"
REGISTRY_STATUS = "registered_needs_final_review"
ALLOWED_REGISTRY_STATUSES = {"registered_needs_final_review", "archived"}
DB_ONLY_NOTICE = (
    "DB-only RAG approved rule candidate registry: use only validated RAG rule "
    "candidate draft reports and the DB-grounded text already present in those "
    "reports. Do not use external web search, current market news, general "
    "economic knowledge, Naver Cafe access, archive writes, or archive.db/data "
    "mutations."
)
TRADING_BOUNDARY_NOTICE = (
    "Trading Bot automatic application is prohibited: this registry update must "
    "not create, export, or modify Trading Bot rules or Trading Bot files."
)
REGISTRY_ONLY_NOTICE = (
    "The RAG rule candidate registry is not a final trading rule registry. "
    "Registered candidates still need final human review and are not approved "
    "for live trading or Trading Bot application."
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
    if not path.exists():
        return []
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


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def stable_registry_id(source_rule_candidate_id: str) -> str:
    digest = hashlib.sha256(f"rag-rule-candidate-registry:{source_rule_candidate_id}".encode("utf-8")).hexdigest()
    return f"rag_rule_candidate_registry_{digest[:16]}"


def source_rule_candidate_id(candidate: dict[str, Any]) -> str:
    return (
        normalize_space(candidate.get("rule_candidate_id"))
        or normalize_space(candidate.get("candidate_id"))
        or normalize_space(candidate.get("draft_id"))
    )


def registry_record_from_candidate(
    *,
    candidate: dict[str, Any],
    source_draft_file: Path,
    timestamp: str,
) -> dict[str, Any]:
    source_id = source_rule_candidate_id(candidate)
    registry_id = stable_registry_id(source_id)
    return {
        "registry_id": registry_id,
        "created_at": timestamp,
        "updated_at": timestamp,
        "source_draft_file": str(source_draft_file),
        "source_rule_candidate_id": source_id,
        "candidate_id": normalize_space(candidate.get("candidate_id")),
        "rule_candidate_id": normalize_space(candidate.get("rule_candidate_id")),
        "source_memory_id": normalize_space(candidate.get("source_memory_id")),
        "rule_candidate_category": normalize_space(candidate.get("rule_candidate_category")),
        "draft_status": normalize_space(candidate.get("draft_status")),
        "registry_status": REGISTRY_STATUS,
        "rule_candidate_summary": normalize_space(candidate.get("rule_candidate_summary")),
        "source_question": normalize_space(candidate.get("source_question")),
        "source_answer": normalize_space(candidate.get("source_answer")),
        "evidence_strength": normalize_space(candidate.get("evidence_strength")),
        "source_refs": coerce_list(candidate.get("source_refs")),
        "used_sources": coerce_list(candidate.get("used_sources")),
        "tags": coerce_list(candidate.get("tags")),
        "boundary_notice": f"{normalize_space(candidate.get('boundary_notice'))} {REGISTRY_ONLY_NOTICE}".strip(),
        "schema_name": draft_schema.SCHEMA_NAME,
        "schema_version": draft_schema.SCHEMA_VERSION,
    }


def registry_keys(rows: Sequence[dict[str, Any]]) -> tuple[set[str], set[str]]:
    registry_ids = {normalize_space(row.get("registry_id")) for row in rows if normalize_space(row.get("registry_id"))}
    source_ids = {
        normalize_space(row.get("source_rule_candidate_id"))
        for row in rows
        if normalize_space(row.get("source_rule_candidate_id"))
    }
    return registry_ids, source_ids


def build_summary(
    *,
    draft_file: Path,
    registry_file: Path,
    candidates: Sequence[dict[str, Any]],
    added_records: Sequence[dict[str, Any]],
    skipped_duplicate_count: int,
    skipped_not_approved_count: int,
    dry_run: bool,
    generated_at: str,
) -> dict[str, Any]:
    approved_count = sum(
        1 for candidate in candidates if normalize_space(candidate.get("draft_status")) == "approved_for_registry"
    )
    return {
        "draft_file": str(draft_file),
        "registry_file": str(registry_file),
        "generated_at": generated_at,
        "candidate_count": len(candidates),
        "approved_for_registry_count": approved_count,
        "added_count": len(added_records),
        "skipped_duplicate_count": skipped_duplicate_count,
        "skipped_not_approved_count": skipped_not_approved_count,
        "stored_registry_ids": [record["registry_id"] for record in added_records],
        "dry_run": dry_run,
        "db_only_notice": DB_ONLY_NOTICE,
        "trading_boundary_notice": TRADING_BOUNDARY_NOTICE,
        "registry_only_notice": REGISTRY_ONLY_NOTICE,
    }


def format_markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# RAG Rule Candidate Registry Update",
        "",
        f"- draft_file: {summary['draft_file']}",
        f"- registry_file: {summary['registry_file']}",
        f"- generated_at: {summary['generated_at']}",
        f"- candidate_count: {summary['candidate_count']}",
        f"- approved_for_registry_count: {summary['approved_for_registry_count']}",
        f"- added_count: {summary['added_count']}",
        f"- skipped_duplicate_count: {summary['skipped_duplicate_count']}",
        f"- skipped_not_approved_count: {summary['skipped_not_approved_count']}",
        f"- dry_run: {str(summary['dry_run']).lower()}",
        f"- stored_registry_ids: {json.dumps(summary['stored_registry_ids'], ensure_ascii=True)}",
        "",
        "## DB-only Boundary",
        "",
        summary["db_only_notice"],
        "",
        "## Trading Bot Boundary",
        "",
        summary["trading_boundary_notice"],
        "",
        "## Registry Boundary",
        "",
        summary["registry_only_notice"],
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_summary_reports(out_dir: Path, timestamp: str, summary: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"rag-rule-candidate-registry-update-{timestamp}.json"
    md_path = out_dir / f"rag-rule-candidate-registry-update-{timestamp}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_markdown_summary(summary), encoding="utf-8", newline="\n")
    return json_path, md_path


def update_registry(
    *,
    draft_file: Path | None = None,
    registry_file: Path = DEFAULT_REGISTRY_FILE,
    out_dir: Path = DEFAULT_REPORTS_DIR,
    dry_run: bool = False,
    timestamp: str | None = None,
) -> tuple[dict[str, Any], Path | None, Path | None]:
    stamp = timestamp or timestamp_now()
    resolved_draft = draft_file or draft_schema.latest_draft_file(DEFAULT_REPORTS_DIR)
    draft_report = draft_schema.read_json_object(resolved_draft)
    validation = draft_schema.validate_report(draft_report, draft_file=resolved_draft)
    blocking_errors = [error for error in validation["errors"] if error.get("field") != "draft_status"]
    if blocking_errors:
        raise ValueError(f"{resolved_draft}: invalid draft schema: {len(blocking_errors)} blocking error(s)")

    candidates = draft_report.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError(f"{resolved_draft}: missing candidates list")

    existing_rows = read_jsonl(registry_file)
    existing_registry_ids, existing_source_ids = registry_keys(existing_rows)
    added_records: list[dict[str, Any]] = []
    skipped_duplicate_count = 0
    skipped_not_approved_count = 0

    for candidate in candidates:
        if normalize_space(candidate.get("draft_status")) != "approved_for_registry":
            skipped_not_approved_count += 1
            continue
        source_id = source_rule_candidate_id(candidate)
        registry_id = stable_registry_id(source_id)
        if registry_id in existing_registry_ids or source_id in existing_source_ids:
            skipped_duplicate_count += 1
            continue
        record = registry_record_from_candidate(candidate=candidate, source_draft_file=resolved_draft, timestamp=stamp)
        added_records.append(record)
        existing_registry_ids.add(record["registry_id"])
        existing_source_ids.add(record["source_rule_candidate_id"])

    summary = build_summary(
        draft_file=resolved_draft,
        registry_file=registry_file,
        candidates=candidates,
        added_records=added_records,
        skipped_duplicate_count=skipped_duplicate_count,
        skipped_not_approved_count=skipped_not_approved_count,
        dry_run=dry_run,
        generated_at=stamp,
    )

    if dry_run:
        return summary, None, None

    if added_records:
        write_jsonl(registry_file, [*existing_rows, *added_records])
    elif not registry_file.exists():
        registry_file.parent.mkdir(parents=True, exist_ok=True)

    json_path, md_path = write_summary_reports(out_dir, stamp, summary)
    return summary, json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append approved RAG rule candidate drafts into the RAG-internal registry.",
        epilog=f"{DB_ONLY_NOTICE} {TRADING_BOUNDARY_NOTICE} {REGISTRY_ONLY_NOTICE}",
    )
    parser.add_argument("--draft-file", type=Path, default=None)
    parser.add_argument("--registry-file", type=Path, default=DEFAULT_REGISTRY_FILE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    try:
        summary, json_path, md_path = update_registry(
            draft_file=args.draft_file,
            registry_file=args.registry_file,
            out_dir=args.out_dir,
            dry_run=args.dry_run,
            timestamp=args.timestamp,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(DB_ONLY_NOTICE)
    print(TRADING_BOUNDARY_NOTICE)
    print(REGISTRY_ONLY_NOTICE)
    print(f"Candidates: {summary['candidate_count']}")
    print(f"Approved for registry: {summary['approved_for_registry_count']}")
    print(f"Added: {summary['added_count']}")
    print(f"Skipped duplicate: {summary['skipped_duplicate_count']}")
    print(f"Skipped not approved: {summary['skipped_not_approved_count']}")
    if args.dry_run:
        print("Dry run: no registry or summary report files written.")
    else:
        print(f"JSON: {json_path}")
        print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
