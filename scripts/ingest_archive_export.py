import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = (
    "article_id",
    "title",
    "body_text",
    "url",
    "author",
    "created_at",
    "collected_at",
    "source",
    "content_hash",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_no}: invalid JSON: {exc.msg}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"line {line_no}: expected JSON object")
            validate_required_fields(record, line_no)
            records.append(record)
    return records


def validate_required_fields(record: dict[str, Any], line_no: int) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        raise ValueError(f"line {line_no}: missing required fields: {', '.join(missing)}")

    empty = [
        field
        for field in REQUIRED_FIELDS
        if record.get(field) is None or str(record.get(field)).strip() == ""
    ]
    if empty:
        raise ValueError(f"line {line_no}: empty required fields: {', '.join(empty)}")


def normalize_article(record: dict[str, Any]) -> dict[str, Any]:
    article_id = int(str(record["article_id"]).strip())
    title = str(record["title"]).strip()
    body_text = str(record["body_text"]).strip()
    created_at = str(record["created_at"]).strip()
    collected_at = str(record["collected_at"]).strip()
    url = str(record["url"]).strip()
    source = str(record["source"]).strip()
    content_hash = str(record["content_hash"]).strip()

    return {
        "article_id": article_id,
        "title": title,
        "clean_text": body_text,
        "posted_at": created_at,
        "created_at": created_at,
        "collected_at": collected_at,
        "url": url,
        "source_url": url,
        "author": str(record["author"]).strip(),
        "source": source,
        "content_hash": content_hash,
        "status": "BODY_COLLECTED",
    }


def normalize_articles(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    seen_article_ids: set[int] = set()
    seen_content_hashes: set[str] = set()
    normalized: list[dict[str, Any]] = []
    stats = {
        "input_records": len(records),
        "normalized_records": 0,
        "duplicate_article_id_skipped": 0,
        "duplicate_content_hash_skipped": 0,
    }

    for record in records:
        article = normalize_article(record)
        article_id = int(article["article_id"])
        content_hash = str(article["content_hash"])

        if article_id in seen_article_ids:
            stats["duplicate_article_id_skipped"] += 1
            continue
        if content_hash in seen_content_hashes:
            stats["duplicate_content_hash_skipped"] += 1
            continue

        seen_article_ids.add(article_id)
        seen_content_hashes.add(content_hash)
        normalized.append(article)

    stats["normalized_records"] = len(normalized)
    return normalized, stats


def summarize(records: list[dict[str, Any]], stats: dict[str, int], dry_run: bool) -> dict[str, Any]:
    sources = Counter(str(record["source"]) for record in records)
    return {
        **stats,
        "dry_run": dry_run,
        "sources": dict(sorted(sources.items())),
    }


def write_jsonl(path: Path, records: list[dict[str, Any]], overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest archive-export JSONL into normalized RAG article records"
    )
    parser.add_argument("--input", type=Path, required=True, help="Archive export JSONL path")
    parser.add_argument("--output", type=Path, help="Normalized JSONL output path")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing --output file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.input.exists():
        print(f"[ERROR] input not found: {args.input}", file=sys.stderr)
        return 1
    if not args.dry_run and args.output is None:
        print("[ERROR] --output is required unless --dry-run is used", file=sys.stderr)
        return 2

    try:
        raw_records = read_jsonl(args.input)
        normalized, stats = normalize_articles(raw_records)
        if not args.dry_run:
            write_jsonl(args.output, normalized, overwrite=args.overwrite)
    except (OSError, ValueError, FileExistsError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    summary = summarize(normalized, stats, dry_run=bool(args.dry_run))
    if args.output is not None:
        summary["output"] = str(args.output)

    print("=== RAG archive export ingest summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
