from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MEMORY_STORE = PROJECT_ROOT / "agent_reports" / "rag_research_memory_store.jsonl"
DB_ONLY_NOTICE = (
    "DB-only research memory store: use only internal DB retrieval outputs, "
    "agent reports, fixtures, and docs. Do not use external web search, current "
    "market news, general economic knowledge, Naver Cafe access, archive writes, "
    "or Trading Bot rule changes."
)
STOREABLE_ANSWER_STATUSES = {"ok", "answer_ok"}
MEMORY_ACTION = "candidate_for_memory_store"


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def timestamp_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def normalize_space(value: Any) -> str:
    return " ".join(str(value or "").replace("\u200b", " ").split())


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


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


def candidate_question_ids(learning_summary: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for candidate in learning_summary.get("next_learning_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("action") != MEMORY_ACTION:
            continue
        question_id = normalize_space(candidate.get("question_id"))
        if question_id:
            ids.add(question_id)
    return ids


def resolve_answer_file(learning_loop_file: Path, explicit_answer_file: Path | None) -> Path:
    if explicit_answer_file is not None:
        return explicit_answer_file
    summary = read_json(learning_loop_file)
    answer_file = summary.get("answer_file")
    if not answer_file:
        raise ValueError("--answer-file is required when learning loop JSON has no answer_file")
    return Path(str(answer_file))


def collect_source_refs(row: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    raw_refs = row.get("source_refs")
    if isinstance(raw_refs, list):
        refs.extend(normalize_space(ref) for ref in raw_refs if normalize_space(ref))
    for source in row.get("used_sources") or []:
        if not isinstance(source, dict):
            continue
        source_ref = normalize_space(source.get("source_ref"))
        if source_ref:
            refs.append(source_ref)
    return list(dict.fromkeys(refs))


def canonical_memory_payload(row: dict[str, Any], source_refs: Sequence[str]) -> dict[str, Any]:
    return {
        "question_id": normalize_space(row.get("question_id")),
        "question": normalize_space(row.get("question")),
        "answer_status": normalize_space(row.get("answer_status")),
        "answer": normalize_space(row.get("answer")),
        "source_refs": list(source_refs),
        "used_sources": row.get("used_sources") or [],
    }


def build_memory_id(row: dict[str, Any], source_refs: Sequence[str]) -> str:
    payload = canonical_memory_payload(row, source_refs)
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "ragmem_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def evidence_strength_for_status(answer_status: str, source_refs: Sequence[str]) -> str:
    if answer_status in STOREABLE_ANSWER_STATUSES and source_refs:
        return "db_grounded"
    if answer_status in STOREABLE_ANSWER_STATUSES:
        return "answer_ok_without_source_refs"
    return "candidate"


def tags_for_row(row: dict[str, Any]) -> list[str]:
    tags = ["rag_research", "db_only", "research_memory"]
    topic = normalize_space(row.get("topic"))
    if topic:
        tags.append(f"topic:{topic}")
    status = normalize_space(row.get("answer_status"))
    if status:
        tags.append(f"answer_status:{status}")
    return tags


def is_store_candidate(row: dict[str, Any], memory_candidate_ids: set[str]) -> bool:
    question_id = normalize_space(row.get("question_id"))
    answer_status = normalize_space(row.get("answer_status"))
    action = normalize_space(row.get("action"))
    return (
        answer_status in STOREABLE_ANSWER_STATUSES
        or action == MEMORY_ACTION
        or bool(question_id and question_id in memory_candidate_ids)
    )


def build_memory_record(
    row: dict[str, Any],
    *,
    created_at: str,
    retrieval_file: str | None,
    answer_file: Path,
    learning_loop_file: Path,
) -> dict[str, Any]:
    source_refs = collect_source_refs(row)
    answer_status = normalize_space(row.get("answer_status"))
    memory_id = build_memory_id(row, source_refs)
    return {
        "memory_id": memory_id,
        "created_at": created_at,
        "question_id": normalize_space(row.get("question_id")),
        "question": normalize_space(row.get("question")),
        "answer_status": answer_status,
        "answer": normalize_space(row.get("answer")),
        "evidence_strength": evidence_strength_for_status(answer_status, source_refs),
        "source_refs": source_refs,
        "used_sources": row.get("used_sources") or [],
        "retrieval_file": retrieval_file,
        "answer_file": str(answer_file),
        "learning_loop_file": str(learning_loop_file),
        "tags": tags_for_row(row),
        "promotion_status": "pending_human_review",
    }


def existing_memory_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return read_jsonl(path)


def format_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# RAG Research Memory Store Update",
        "",
        f"- learning_loop_file: {summary['learning_loop_file']}",
        f"- answer_file: {summary['answer_file']}",
        f"- memory_store_file: {summary['memory_store_file']}",
        f"- candidate_count: {summary['candidate_count']}",
        f"- added_count: {summary['added_count']}",
        f"- skipped_duplicate_count: {summary['skipped_duplicate_count']}",
        f"- skipped_non_ok_count: {summary['skipped_non_ok_count']}",
        f"- dry_run: {str(summary['dry_run']).lower()}",
        "",
        "## DB-only Safety",
        "",
        summary["db_only_notice"],
        "",
        "## Stored Memory IDs",
        "",
    ]
    lines.extend([f"- {memory_id}" for memory_id in summary["stored_memory_ids"]] or ["- none"])
    return "\n".join(lines).rstrip() + "\n"


def write_summary_reports(report_dir: Path, stamp: str, summary: dict[str, Any]) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"rag-research-memory-update-{stamp}.json"
    md_path = report_dir / f"rag-research-memory-update-{stamp}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_markdown_report(summary), encoding="utf-8", newline="\n")
    return json_path, md_path


def update_memory_store(
    *,
    learning_loop_file: Path,
    answer_file: Path | None = None,
    out_file: Path = DEFAULT_MEMORY_STORE,
    dry_run: bool = False,
    timestamp: str | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    stamp = timestamp or timestamp_now()
    learning_summary = read_json(learning_loop_file)
    resolved_answer_file = resolve_answer_file(learning_loop_file, answer_file)
    answer_records = read_jsonl(resolved_answer_file)
    memory_candidate_ids = candidate_question_ids(learning_summary)
    existing_records = existing_memory_records(out_file)
    existing_ids = {
        normalize_space(record.get("memory_id"))
        for record in existing_records
        if normalize_space(record.get("memory_id"))
    }

    candidate_count = 0
    skipped_non_ok_count = 0
    skipped_duplicate_count = 0
    added_records: list[dict[str, Any]] = []
    stored_memory_ids: list[str] = []
    retrieval_file = learning_summary.get("retrieval_file")
    retrieval_file_text = str(retrieval_file) if retrieval_file not in (None, "") else None

    for row in answer_records:
        if not is_store_candidate(row, memory_candidate_ids):
            skipped_non_ok_count += 1
            continue
        candidate_count += 1
        record = build_memory_record(
            row,
            created_at=stamp,
            retrieval_file=retrieval_file_text,
            answer_file=resolved_answer_file,
            learning_loop_file=learning_loop_file,
        )
        memory_id = record["memory_id"]
        if memory_id in existing_ids:
            skipped_duplicate_count += 1
            continue
        existing_ids.add(memory_id)
        added_records.append(record)
        stored_memory_ids.append(memory_id)

    if not dry_run and added_records:
        write_jsonl(out_file, [*existing_records, *added_records])

    summary = {
        "generated_at": stamp,
        "learning_loop_file": str(learning_loop_file),
        "answer_file": str(resolved_answer_file),
        "memory_store_file": str(out_file),
        "candidate_count": candidate_count,
        "added_count": len(added_records),
        "skipped_duplicate_count": skipped_duplicate_count,
        "skipped_non_ok_count": skipped_non_ok_count,
        "stored_memory_ids": stored_memory_ids,
        "dry_run": dry_run,
        "db_only_notice": DB_ONLY_NOTICE,
    }
    json_path, md_path = write_summary_reports(out_file.parent, stamp, summary)
    return summary, json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Append DB-only answer_ok or candidate_for_memory_store RAG research "
            "answers into an idempotent JSONL memory store."
        ),
        epilog=DB_ONLY_NOTICE,
    )
    parser.add_argument("--learning-loop-file", type=Path, required=True)
    parser.add_argument("--answer-file", type=Path, default=None)
    parser.add_argument("--out-file", type=Path, default=DEFAULT_MEMORY_STORE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    try:
        summary, json_path, md_path = update_memory_store(
            learning_loop_file=args.learning_loop_file,
            answer_file=args.answer_file,
            out_file=args.out_file,
            dry_run=args.dry_run,
            timestamp=args.timestamp,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(DB_ONLY_NOTICE)
    print(f"Candidates: {summary['candidate_count']}")
    print(f"Added: {summary['added_count']}")
    print(f"Skipped duplicates: {summary['skipped_duplicate_count']}")
    print(f"Skipped non-ok: {summary['skipped_non_ok_count']}")
    print(f"Memory store: {summary['memory_store_file']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
