from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MEMORY_STORE = PROJECT_ROOT / "agent_reports" / "rag_research_memory_store.jsonl"
ALLOWED_STATUSES = {"pending", "approved", "rejected"}
DB_ONLY_NOTICE = (
    "DB-only promotion status update: approval only records human review state "
    "inside the RAG research memory store. It must not use external web search, "
    "Naver Cafe access, archive writes, or Trading Bot file changes."
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


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def build_review_payload(
    *,
    status: str,
    note: str | None,
    reviewer: str | None,
    reviewed_at: str,
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    existing_payload = existing if isinstance(existing, dict) else {}
    payload = {
        "status": status,
        "note": normalize_space(note),
        "reviewer": normalize_space(reviewer),
        "reviewed_at": reviewed_at,
    }
    comparable_existing = {
        "status": normalize_space(existing_payload.get("status")),
        "note": normalize_space(existing_payload.get("note")),
        "reviewer": normalize_space(existing_payload.get("reviewer")),
    }
    comparable_new = {
        "status": payload["status"],
        "note": payload["note"],
        "reviewer": payload["reviewer"],
    }
    if comparable_existing == comparable_new and normalize_space(existing_payload.get("reviewed_at")):
        payload["reviewed_at"] = normalize_space(existing_payload.get("reviewed_at"))
    return payload


def update_promotion_status(
    *,
    memory_store_file: Path = DEFAULT_MEMORY_STORE,
    memory_id: str,
    status: str,
    note: str | None = None,
    reviewer: str | None = None,
    dry_run: bool = False,
    timestamp: str | None = None,
) -> dict[str, Any]:
    normalized_status = normalize_space(status)
    if normalized_status not in ALLOWED_STATUSES:
        raise ValueError(f"--status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}")
    normalized_memory_id = normalize_space(memory_id)
    if not normalized_memory_id:
        raise ValueError("--memory-id is required")

    rows = read_jsonl(memory_store_file)
    found = False
    changed = False
    reviewed_at = timestamp or timestamp_now()

    for row in rows:
        if normalize_space(row.get("memory_id")) != normalized_memory_id:
            continue
        found = True
        old_row = json.dumps(row, ensure_ascii=True, sort_keys=True)
        row["promotion_status"] = normalized_status
        row["promotion_review"] = build_review_payload(
            status=normalized_status,
            note=note,
            reviewer=reviewer,
            reviewed_at=reviewed_at,
            existing=row.get("promotion_review"),
        )
        new_row = json.dumps(row, ensure_ascii=True, sort_keys=True)
        changed = old_row != new_row
        break

    if not found:
        raise KeyError(f"memory_id not found: {normalized_memory_id}")
    if changed and not dry_run:
        write_jsonl(memory_store_file, rows)

    return {
        "memory_store_file": str(memory_store_file),
        "memory_id": normalized_memory_id,
        "status": normalized_status,
        "dry_run": dry_run,
        "changed": changed,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update human promotion status for one RAG research memory record.",
        epilog=DB_ONLY_NOTICE,
    )
    parser.add_argument("--memory-store-file", type=Path, default=DEFAULT_MEMORY_STORE)
    parser.add_argument("--memory-id", required=True)
    parser.add_argument("--status", required=True, choices=sorted(ALLOWED_STATUSES))
    parser.add_argument("--note", default=None)
    parser.add_argument("--reviewer", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    try:
        summary = update_promotion_status(
            memory_store_file=args.memory_store_file,
            memory_id=args.memory_id,
            status=args.status,
            note=args.note,
            reviewer=args.reviewer,
            dry_run=args.dry_run,
            timestamp=args.timestamp,
        )
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(DB_ONLY_NOTICE)
    print(f"Memory ID: {summary['memory_id']}")
    print(f"Status: {summary['status']}")
    print(f"Changed: {str(summary['changed']).lower()}")
    print(f"Dry run: {str(summary['dry_run']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
