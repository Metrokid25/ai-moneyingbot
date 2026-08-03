"""Verify that every rulebook gold chunk exists in Qdrant with provenance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path.cwd()
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rag_qdrant import chunk_id_to_point_id  # noqa: E402
from rag_retrieval import open_qdrant_client  # noqa: E402


def read_gold_ids(path: Path) -> list[str]:
    values: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            row = json.loads(line)
            values.update(str(value) for value in row.get("expected_chunk_ids") or [])
    return sorted(values)


def summarize_points(expected_ids: list[str], points: list[Any]) -> dict[str, Any]:
    payloads = {
        str((getattr(point, "payload", None) or {}).get("chunk_id")): (
            getattr(point, "payload", None) or {}
        )
        for point in points
    }
    missing = [chunk_id for chunk_id in expected_ids if chunk_id not in payloads]
    mismatches = [
        chunk_id
        for chunk_id in expected_ids
        if chunk_id in payloads
        and str(payloads[chunk_id].get("article_id")) != chunk_id.split(":", 1)[0]
    ]
    empty_text = [
        chunk_id
        for chunk_id in expected_ids
        if chunk_id in payloads and not str(payloads[chunk_id].get("text") or "").strip()
    ]
    return {
        "expected_chunk_count": len(expected_ids),
        "retrieved_chunk_count": len(payloads),
        "missing_chunk_ids": missing,
        "article_id_mismatch_chunk_ids": mismatches,
        "empty_text_chunk_ids": empty_text,
        "validation": "passed" if not missing and not mismatches and not empty_text else "failed",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--qdrant-path", type=Path, default=Path("data/qdrant"))
    parser.add_argument("--collection", default="goodmorning_chunks")
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expected_ids = read_gold_ids(args.gold.resolve())
    client = open_qdrant_client(args.qdrant_path.resolve())
    try:
        points = client.retrieve(
            collection_name=args.collection,
            ids=[chunk_id_to_point_id(chunk_id) for chunk_id in expected_ids],
            with_payload=True,
            with_vectors=False,
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    summary = summarize_points(expected_ids, list(points))
    text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if summary["validation"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
