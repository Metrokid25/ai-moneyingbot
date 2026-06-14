from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "agent_reports"
DRAFT_GLOBS = (
    "rag-approved-memory-rule-candidates-*.json",
    "rag-approved-memory-rule-candidate-draft-*.json",
)
SCHEMA_NAME = "rag_rule_candidate_draft"
SCHEMA_VERSION = 1
ALLOWED_DRAFT_STATUSES = {"draft_needs_human_review", "rejected", "approved_for_registry"}
ALLOWED_CATEGORIES = {"principle", "pattern", "risk_control", "watch_condition", "unresolved"}
DB_ONLY_NOTICE = (
    "DB-only RAG rule candidate schema validation: use only RAG-internal draft "
    "reports generated from approved memory export previews. Do not use external "
    "web search, current market news, general economic knowledge, Naver Cafe "
    "access, archive writes, or archive.db/data mutations."
)
TRADING_BOUNDARY_NOTICE = (
    "Trading Bot automatic application is prohibited: validation must not create, "
    "export, or modify Trading Bot rules or Trading Bot files."
)
DRAFT_ONLY_NOTICE = (
    "A valid RAG rule candidate draft is not a final trading rule and still "
    "requires human review."
)
TOP_LEVEL_REQUIRED_FIELDS = (
    "schema_name",
    "schema_version",
    "generated_at",
    "preview_file",
    "candidate_count",
    "candidates",
    "db_only_notice",
    "trading_boundary_notice",
    "draft_only_notice",
)
CANDIDATE_REQUIRED_FIELDS = (
    "candidate_id",
    "rule_candidate_id",
    "source_memory_id",
    "draft_status",
    "rule_candidate_category",
    "suggested_export_category",
    "draft_summary",
    "rule_candidate_summary",
    "draft_rule_candidate_summary",
    "source_question",
    "question",
    "source_answer",
    "answer",
    "evidence_strength",
    "source_refs",
    "used_sources",
    "tags",
    "boundary_notice",
)


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def timestamp_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def normalize_space(value: Any) -> str:
    return " ".join(str(value or "").replace("\u200b", " ").split())


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: report must be a JSON object")
    return value


def latest_draft_file(reports_dir: Path = DEFAULT_REPORTS_DIR) -> Path:
    matches: list[Path] = []
    for pattern in DRAFT_GLOBS:
        matches.extend(reports_dir.glob(pattern))
    matches = sorted(set(matches))
    if not matches:
        raise FileNotFoundError(f"no RAG rule candidate draft JSON found in {reports_dir}")
    return matches[-1]


def has_non_empty_field(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(normalize_space(value))
    if isinstance(value, list):
        return True
    if isinstance(value, dict):
        return True
    return True


def contains_all(text: str, fragments: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return all(fragment.lower() in lowered for fragment in fragments)


def add_error(errors: list[dict[str, Any]], *, scope: str, field: str, message: str) -> None:
    errors.append({"scope": scope, "field": field, "message": message})


def validate_top_level(report: dict[str, Any], errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for field in TOP_LEVEL_REQUIRED_FIELDS:
        if field not in report or not has_non_empty_field(report.get(field)):
            add_error(errors, scope="top_level", field=field, message="missing required field")

    if report.get("schema_name") != SCHEMA_NAME:
        add_error(errors, scope="top_level", field="schema_name", message=f"must be {SCHEMA_NAME}")
    if report.get("schema_version") != SCHEMA_VERSION:
        add_error(errors, scope="top_level", field="schema_version", message=f"must be {SCHEMA_VERSION}")
    if not isinstance(report.get("candidates"), list):
        add_error(errors, scope="top_level", field="candidates", message="must be a list")
    if not isinstance(report.get("candidate_count"), int):
        add_error(errors, scope="top_level", field="candidate_count", message="must be an integer")
    elif isinstance(report.get("candidates"), list) and report["candidate_count"] != len(report["candidates"]):
        add_error(errors, scope="top_level", field="candidate_count", message="must match candidates length")

    boundary_text = " ".join(
        normalize_space(report.get(field))
        for field in ("db_only_notice", "trading_boundary_notice", "draft_only_notice")
    )
    if not contains_all(boundary_text, ("DB-only",)):
        add_error(errors, scope="top_level", field="db_only_notice", message="must include DB-only boundary")
    if not contains_all(boundary_text, ("Trading Bot",)):
        add_error(errors, scope="top_level", field="trading_boundary_notice", message="must include Trading Bot boundary")
    if not contains_all(boundary_text, ("not a final",)) and not contains_all(boundary_text, ("not confirmed",)):
        add_error(errors, scope="top_level", field="draft_only_notice", message="must state draft is not final rule")
    return errors


def validate_candidate(candidate: Any, index: int, errors: list[dict[str, Any]]) -> None:
    scope = f"candidate[{index}]"
    if not isinstance(candidate, dict):
        add_error(errors, scope=scope, field="candidate", message="must be an object")
        return

    candidate_id = normalize_space(candidate.get("candidate_id")) or normalize_space(candidate.get("draft_id"))
    if candidate_id:
        scope = f"candidate[{index}:{candidate_id}]"

    for field in CANDIDATE_REQUIRED_FIELDS:
        if field not in candidate or not has_non_empty_field(candidate.get(field)):
            add_error(errors, scope=scope, field=field, message="missing required field")

    status = normalize_space(candidate.get("draft_status"))
    if status and status not in ALLOWED_DRAFT_STATUSES:
        add_error(errors, scope=scope, field="draft_status", message="invalid draft status")

    category = normalize_space(candidate.get("rule_candidate_category")) or normalize_space(
        candidate.get("suggested_export_category")
    )
    if category and category not in ALLOWED_CATEGORIES:
        add_error(errors, scope=scope, field="rule_candidate_category", message="invalid category")
    suggested = normalize_space(candidate.get("suggested_export_category"))
    if suggested and suggested not in ALLOWED_CATEGORIES:
        add_error(errors, scope=scope, field="suggested_export_category", message="invalid category")

    for field in ("source_refs", "used_sources", "tags"):
        if field in candidate and not isinstance(candidate.get(field), list):
            add_error(errors, scope=scope, field=field, message="must be a list")

    boundary_text = normalize_space(candidate.get("boundary_notice"))
    if boundary_text:
        if "Trading Bot" not in boundary_text:
            add_error(errors, scope=scope, field="boundary_notice", message="must include Trading Bot boundary")
        if "not a rule export" not in boundary_text and "not a final" not in boundary_text:
            add_error(errors, scope=scope, field="boundary_notice", message="must state draft is not final rule")


def validate_report(report: dict[str, Any], *, draft_file: Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    validate_top_level(report, errors)
    candidates = report.get("candidates")
    if isinstance(candidates, list):
        for index, candidate in enumerate(candidates, start=1):
            validate_candidate(candidate, index, errors)

    return {
        "draft_file": str(draft_file),
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "valid": not errors,
        "error_count": len(errors),
        "candidate_count": len(candidates) if isinstance(candidates, list) else 0,
        "errors": errors,
        "db_only_notice": DB_ONLY_NOTICE,
        "trading_boundary_notice": TRADING_BOUNDARY_NOTICE,
        "draft_only_notice": DRAFT_ONLY_NOTICE,
    }


def write_summary(out_file: Path, summary: dict[str, Any]) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_draft_file(
    *,
    draft_file: Path | None = None,
    out_file: Path | None = None,
    output_format: str = "text",
    dry_run: bool = False,
) -> tuple[dict[str, Any], Path]:
    resolved_draft = draft_file or latest_draft_file(DEFAULT_REPORTS_DIR)
    report = read_json_object(resolved_draft)
    summary = validate_report(report, draft_file=resolved_draft)
    if out_file is not None and not dry_run:
        write_summary(out_file, summary)
    return summary, resolved_draft


def format_text_summary(summary: dict[str, Any]) -> str:
    lines = [
        DB_ONLY_NOTICE,
        TRADING_BOUNDARY_NOTICE,
        DRAFT_ONLY_NOTICE,
        f"draft_file: {summary['draft_file']}",
        f"schema_name: {summary['schema_name']}",
        f"schema_version: {summary['schema_version']}",
        f"valid: {str(summary['valid']).lower()}",
        f"candidate_count: {summary['candidate_count']}",
        f"error_count: {summary['error_count']}",
    ]
    for error in summary["errors"]:
        lines.append(f"- {error['scope']} {error['field']}: {error['message']}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate frozen RAG rule candidate draft schema reports.",
        epilog=f"{DB_ONLY_NOTICE} {TRADING_BOUNDARY_NOTICE} {DRAFT_ONLY_NOTICE}",
    )
    parser.add_argument("--draft-file", type=Path, default=None)
    parser.add_argument("--out-file", type=Path, default=None)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    try:
        summary, _draft_file = validate_draft_file(
            draft_file=args.draft_file,
            out_file=args.out_file,
            output_format=args.format,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        print(format_text_summary(summary))
    return 0 if summary["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
