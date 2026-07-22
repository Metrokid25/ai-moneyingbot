"""Read-only preflight for unattended RAG incremental indexing.

The production wrapper runs this check before it can invoke the indexer.  It
validates that the local Qdrant collection and its manifest (or one-time seed
IDs) describe the same baseline, so a missing/stale baseline cannot turn a
small incremental run into a full-corpus Voyage embedding bill.

This script never opens Qdrant through QdrantClient.  It reads meta.json and
the collection SQLite file with ``mode=ro`` + ``PRAGMA query_only=ON``.
"""

from __future__ import annotations

import argparse
import base64
import json
import pickletools
import re
import sqlite3
import sys
import urllib.parse
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from rag_qdrant import chunk_id_to_point_id  # noqa: E402


DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "archive.db"
DEFAULT_QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "data" / "rag_index_manifest.jsonl"
DEFAULT_SEED_IDS_PATH = PROJECT_ROOT / "data" / "embeddings_phase2_ids.npy"
DEFAULT_COLLECTION = "goodmorning_chunks"
EXPECTED_VECTOR_SIZE = 1024
EXPECTED_DISTANCE = "cosine"
CHUNK_ID_RE = re.compile(r"^[1-9]\d*:(?:0|[1-9]\d*)$")


class AssetCheckError(RuntimeError):
    """A deployment asset is absent, malformed, or inconsistent."""


@dataclass(frozen=True)
class BaselineInfo:
    source: str
    path: Path
    ids_count: int
    unique_ids_count: int
    chunk_ids: frozenset[str]


def _sqlite_uri(path: Path) -> str:
    quoted = urllib.parse.quote(path.resolve().as_posix(), safe="/:")
    return f"file:{quoted}?mode=ro"


def _open_sqlite_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise AssetCheckError(f"SQLite file not found: {path}")
    conn = sqlite3.connect(_sqlite_uri(path), uri=True)
    conn.execute("PRAGMA query_only=ON")
    if conn.execute("PRAGMA query_only").fetchone()[0] != 1:
        conn.close()
        raise AssetCheckError(f"failed to enforce SQLite query_only mode: {path}")
    return conn


def load_manifest_info(path: Path) -> BaselineInfo:
    ids: list[str] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for line_no, raw_line in enumerate(fh, 1):
            line = raw_line.strip()
            if not line:
                raise AssetCheckError(f"blank manifest line at {path}:{line_no}")
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AssetCheckError(f"invalid manifest JSON at {path}:{line_no}: {exc}") from exc
            chunk_id = record.get("chunk_id") if isinstance(record, dict) else None
            if not isinstance(chunk_id, str) or not CHUNK_ID_RE.fullmatch(chunk_id):
                raise AssetCheckError(
                    f"invalid chunk_id at {path}:{line_no}: expected '<article_id>:<chunk_index>' string"
                )
            ids.append(chunk_id)

    if not ids:
        raise AssetCheckError(f"manifest is empty: {path}")
    unique_count = len(set(ids))
    if unique_count != len(ids):
        raise AssetCheckError(
            f"duplicate manifest chunk_ids: rows={len(ids)}, unique={unique_count}, path={path}"
        )
    return BaselineInfo("manifest", path, len(ids), unique_count, frozenset(ids))


def load_seed_info(path: Path) -> BaselineInfo:
    try:
        values = np.load(path, allow_pickle=False)
    except Exception as exc:  # noqa: BLE001 - turn numpy details into a clean preflight error
        raise AssetCheckError(f"failed to load seed IDs {path}: {exc}") from exc
    if not isinstance(values, np.ndarray) or values.ndim != 1:
        shape = getattr(values, "shape", None)
        raise AssetCheckError(f"seed IDs must be a 1D numpy array: path={path}, shape={shape}")
    raw_ids = values.tolist()
    if not raw_ids or any(not isinstance(value, str) for value in raw_ids):
        raise AssetCheckError(f"seed IDs must be non-empty strings: {path}")
    ids = [value.strip() for value in raw_ids]
    if any(not CHUNK_ID_RE.fullmatch(chunk_id) for chunk_id in ids):
        raise AssetCheckError(
            f"seed IDs contain invalid chunk_id values; expected '<article_id>:<chunk_index>': {path}"
        )
    unique_count = len(set(ids))
    if unique_count != len(ids):
        raise AssetCheckError(
            f"duplicate seed chunk_ids: rows={len(ids)}, unique={unique_count}, path={path}"
        )
    return BaselineInfo("seed", path, len(ids), unique_count, frozenset(ids))


def load_baseline_info(manifest_path: Path, seed_ids_path: Path) -> BaselineInfo:
    # A present manifest is authoritative.  Never hide a corrupt manifest by
    # silently falling back to an older seed file.
    if manifest_path.is_file():
        return load_manifest_info(manifest_path)
    if seed_ids_path.is_file():
        return load_seed_info(seed_ids_path)
    raise AssetCheckError(
        "no index baseline found: expected manifest or seed IDs; "
        f"manifest={manifest_path}, seed={seed_ids_path}"
    )


def _decode_stored_point_id(stored_id: Any) -> str:
    """Decode qdrant-client local persistence without executing pickle code."""
    if not isinstance(stored_id, str):
        raise AssetCheckError(f"Qdrant point id must be stored as text, got {type(stored_id).__name__}")
    try:
        raw = base64.b64decode(stored_id, validate=True)
        operations = list(pickletools.genops(raw))
    except Exception as exc:  # noqa: BLE001 - report corrupt/unknown persistence as fail-closed
        raise AssetCheckError(f"invalid Qdrant point id encoding: {exc}") from exc

    allowed_ops = {"PROTO", "FRAME", "SHORT_BINUNICODE", "BINUNICODE", "BINUNICODE8", "MEMOIZE", "STOP"}
    if any(op.name not in allowed_ops for op, _arg, _pos in operations):
        names = [op.name for op, _arg, _pos in operations]
        raise AssetCheckError(f"unsupported Qdrant point id pickle operations: {names}")
    values = [
        arg
        for op, arg, _pos in operations
        if op.name in {"SHORT_BINUNICODE", "BINUNICODE", "BINUNICODE8"}
    ]
    if len(values) != 1 or not isinstance(values[0], str):
        raise AssetCheckError("Qdrant point id encoding did not contain exactly one string")
    try:
        parsed = uuid.UUID(values[0])
    except ValueError as exc:
        raise AssetCheckError(f"Qdrant point id is not a UUID: {values[0]}") from exc
    if parsed.version != 5 or str(parsed) != values[0]:
        raise AssetCheckError(f"Qdrant point id is not a canonical UUID5: {values[0]}")
    return values[0]


def inspect_qdrant(qdrant_path: Path, collection: str) -> tuple[dict[str, Any], frozenset[str]]:
    meta_path = qdrant_path / "meta.json"
    if not meta_path.is_file():
        raise AssetCheckError(f"Qdrant meta.json not found: {meta_path}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssetCheckError(f"failed to read Qdrant metadata {meta_path}: {exc}") from exc

    config = meta.get("collections", {}).get(collection)
    if not isinstance(config, dict):
        raise AssetCheckError(f"Qdrant collection not found in metadata: {collection}")
    vectors = config.get("vectors")
    if not isinstance(vectors, dict):
        raise AssetCheckError(f"Qdrant vector config missing for collection: {collection}")
    vector_size = vectors.get("size")
    distance = str(vectors.get("distance", "")).lower()
    if vector_size != EXPECTED_VECTOR_SIZE:
        raise AssetCheckError(
            f"Qdrant vector size mismatch: expected={EXPECTED_VECTOR_SIZE}, actual={vector_size}"
        )
    if distance != EXPECTED_DISTANCE:
        raise AssetCheckError(
            f"Qdrant distance mismatch: expected={EXPECTED_DISTANCE}, actual={distance or '(missing)'}"
        )

    storage_path = qdrant_path / "collection" / collection / "storage.sqlite"
    conn = _open_sqlite_readonly(storage_path)
    try:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='points'"
        ).fetchone()
        if table is None:
            raise AssetCheckError(f"Qdrant points table missing: {storage_path}")
        stored_ids = [row[0] for row in conn.execute("SELECT id FROM points")]
    finally:
        conn.close()
    point_ids = [_decode_stored_point_id(stored_id) for stored_id in stored_ids]
    unique_point_ids = frozenset(point_ids)
    if len(unique_point_ids) != len(point_ids):
        raise AssetCheckError(
            f"duplicate decoded Qdrant point ids: rows={len(point_ids)}, unique={len(unique_point_ids)}"
        )
    return {
        "path": str(qdrant_path),
        "collection": collection,
        "points_count": len(point_ids),
        "vector_size": vector_size,
        "distance": vectors.get("distance"),
        "sqlite_query_only": True,
    }, unique_point_ids


def inspect_archive_db(db_path: Path) -> dict[str, Any]:
    conn = _open_sqlite_readonly(db_path)
    try:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='articles'"
        ).fetchone()
        if table is None:
            raise AssetCheckError(f"archive DB articles table missing: {db_path}")
        readable = conn.execute("SELECT 1 FROM articles LIMIT 1").fetchone()
        if readable is None:
            raise AssetCheckError(f"archive DB articles table is empty: {db_path}")
    finally:
        conn.close()
    return {"path": str(db_path), "readable": True, "sqlite_query_only": True}


def check_assets(
    *,
    db_path: Path,
    qdrant_path: Path,
    manifest_path: Path,
    seed_ids_path: Path,
    collection: str,
) -> dict[str, Any]:
    baseline = load_baseline_info(manifest_path, seed_ids_path)
    qdrant, actual_point_ids = inspect_qdrant(qdrant_path, collection)
    archive_db = inspect_archive_db(db_path)
    if qdrant["points_count"] != baseline.unique_ids_count:
        raise AssetCheckError(
            "Qdrant/baseline count mismatch: "
            f"points={qdrant['points_count']}, baseline_unique_ids={baseline.unique_ids_count}, "
            f"baseline_source={baseline.source}, baseline_path={baseline.path}"
        )
    expected_point_ids = frozenset(chunk_id_to_point_id(chunk_id) for chunk_id in baseline.chunk_ids)
    if actual_point_ids != expected_point_ids:
        missing = sorted(expected_point_ids - actual_point_ids)
        extra = sorted(actual_point_ids - expected_point_ids)
        raise AssetCheckError(
            "Qdrant/baseline point ID set mismatch: "
            f"missing={len(missing)}, extra={len(extra)}, "
            f"missing_sample={missing[:3]}, extra_sample={extra[:3]}, "
            f"baseline_source={baseline.source}, baseline_path={baseline.path}"
        )
    qdrant["point_ids_match_baseline"] = True
    return {
        "status": "PASS",
        "archive_db": archive_db,
        "qdrant": qdrant,
        "baseline": {
            "source": baseline.source,
            "path": str(baseline.path),
            "ids_count": baseline.ids_count,
            "unique_ids_count": baseline.unique_ids_count,
        },
        "write_performed": False,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only safety check for RAG deployment assets before incremental indexing."
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--qdrant-path", type=Path, default=DEFAULT_QDRANT_PATH)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--seed-ids-path", type=Path, default=DEFAULT_SEED_IDS_PATH)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = check_assets(
            db_path=args.db_path,
            qdrant_path=args.qdrant_path,
            manifest_path=args.manifest_path,
            seed_ids_path=args.seed_ids_path,
            collection=args.collection,
        )
    except Exception as exc:  # noqa: BLE001 - stable machine-readable failure for the scheduler
        print(
            json.dumps(
                {"status": "FAIL", "error": str(exc), "write_performed": False},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
