from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_chunking import REQUIRED_METADATA_FIELDS


def read_chunks_jsonl(path: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                chunk = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_no}: invalid JSON: {exc.msg}") from exc
            if not isinstance(chunk, dict):
                raise ValueError(f"line {line_no}: expected JSON object")
            chunks.append(chunk)
    return chunks


def source_candidate_key(chunk: dict[str, Any]) -> str | None:
    metadata = chunk.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    for field in ("content_hash", "source_url", "url"):
        value = metadata.get(field) or chunk.get(field)
        if value is not None and str(value).strip():
            return f"{field}:{str(value).strip()}"

    article_id = metadata.get("article_id") or chunk.get("article_id")
    if article_id is not None and str(article_id).strip():
        return f"article_id:{str(article_id).strip()}"
    return None


def build_quality_report(
    chunks: list[dict[str, Any]],
    min_chars: int,
    max_chars: int,
) -> dict[str, Any]:
    if min_chars < 0:
        raise ValueError("min_chars must be non-negative")
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if min_chars > max_chars:
        raise ValueError("min_chars must be less than or equal to max_chars")

    chunk_ids = [str(chunk.get("chunk_id", "")).strip() for chunk in chunks]
    chunk_id_counts = Counter(chunk_id for chunk_id in chunk_ids if chunk_id)
    source_keys = [source_candidate_key(chunk) for chunk in chunks]
    source_counts = Counter(key for key in source_keys if key)

    empty_chunks: list[str] = []
    too_short_chunks: list[dict[str, Any]] = []
    too_long_chunks: list[dict[str, Any]] = []
    missing_metadata_chunks: list[dict[str, Any]] = []

    for index, chunk in enumerate(chunks):
        chunk_id = str(chunk.get("chunk_id", f"line:{index + 1}")).strip()
        text = str(chunk.get("embedding_text") or "")
        text_len = len(text.strip())

        if text_len == 0:
            empty_chunks.append(chunk_id)
        elif text_len < min_chars:
            too_short_chunks.append({"chunk_id": chunk_id, "length": text_len})
        elif text_len > max_chars:
            too_long_chunks.append({"chunk_id": chunk_id, "length": text_len})

        metadata = chunk.get("metadata")
        if not isinstance(metadata, dict):
            missing = sorted(REQUIRED_METADATA_FIELDS)
        else:
            missing = sorted(
                field
                for field in REQUIRED_METADATA_FIELDS
                if field not in metadata
                or metadata[field] is None
                or (isinstance(metadata[field], str) and not metadata[field].strip())
            )
        if missing:
            missing_metadata_chunks.append({"chunk_id": chunk_id, "missing": missing})

    duplicate_chunk_ids = [
        {"chunk_id": chunk_id, "count": count}
        for chunk_id, count in sorted(chunk_id_counts.items())
        if count > 1
    ]
    duplicate_source_candidates = [
        {"source": key, "count": count}
        for key, count in sorted(source_counts.items())
        if count > 1
    ]

    issue_counts = {
        "empty_chunks": len(empty_chunks),
        "too_short_chunks": len(too_short_chunks),
        "too_long_chunks": len(too_long_chunks),
        "missing_metadata_chunks": len(missing_metadata_chunks),
        "duplicate_chunk_ids": len(duplicate_chunk_ids),
        "duplicate_source_candidates": len(duplicate_source_candidates),
    }

    return {
        "total_chunks": len(chunks),
        "min_chars": min_chars,
        "max_chars": max_chars,
        "issue_counts": issue_counts,
        "empty_chunks": empty_chunks,
        "too_short_chunks": too_short_chunks,
        "too_long_chunks": too_long_chunks,
        "missing_metadata_chunks": missing_metadata_chunks,
        "duplicate_chunk_ids": duplicate_chunk_ids,
        "duplicate_source_candidates": duplicate_source_candidates,
    }


def format_text_report(report: dict[str, Any], chunks_path: Path) -> str:
    lines = [
        "=== RAG chunk quality report ===",
        f"chunks_path: {chunks_path}",
        f"total_chunks: {report['total_chunks']}",
        f"min_chars: {report['min_chars']}",
        f"max_chars: {report['max_chars']}",
        "",
        "issue_counts:",
    ]
    for key, value in report["issue_counts"].items():
        lines.append(f"  {key}: {value}")

    detail_sections = (
        "empty_chunks",
        "too_short_chunks",
        "too_long_chunks",
        "missing_metadata_chunks",
        "duplicate_chunk_ids",
        "duplicate_source_candidates",
    )
    for section in detail_sections:
        values = report[section]
        lines.extend(["", f"{section}:"])
        if not values:
            lines.append("  (none)")
            continue
        for value in values:
            lines.append(f"  - {json.dumps(value, ensure_ascii=False, sort_keys=True)}")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report read-only quality metrics for RAG chunk JSONL")
    parser.add_argument("--chunks-path", type=Path, required=True)
    parser.add_argument("--min-chars", type=int, default=20)
    parser.add_argument("--max-chars", type=int, default=2500)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--out-path",
        type=Path,
        default=None,
        help="Optional report output path. When omitted, the report is printed to stdout.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.chunks_path.exists():
        print(f"[ERROR] chunks JSONL not found: {args.chunks_path}", file=sys.stderr)
        return 1

    try:
        chunks = read_chunks_jsonl(args.chunks_path)
        report = build_quality_report(chunks, min_chars=args.min_chars, max_chars=args.max_chars)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    else:
        output = format_text_report(report, args.chunks_path)

    if args.out_path is None:
        print(output)
    else:
        args.out_path.parent.mkdir(parents=True, exist_ok=True)
        args.out_path.write_text(output + "\n", encoding="utf-8")
        print(f"Report written to {args.out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
