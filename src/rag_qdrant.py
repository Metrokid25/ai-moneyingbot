import json
import uuid
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
except ModuleNotFoundError:
    QdrantClient = None

    class Distance:
        COSINE = "Cosine"

    class PointStruct:
        def __init__(self, id: str, vector: list[float], payload: dict[str, Any]):
            self.id = id
            self.vector = vector
            self.payload = payload

    class VectorParams:
        def __init__(self, size: int, distance: str):
            self.size = size
            self.distance = distance

from rag_chunking import REQUIRED_METADATA_FIELDS


DEFAULT_QDRANT_PATH = "data/qdrant"
DEFAULT_COLLECTION = "goodmorning_chunks"
DEFAULT_VECTOR_SIZE = 1024
DEFAULT_DISTANCE = "cosine"
POINT_ID_NAMESPACE = uuid.UUID("a5ee1b04-3f66-5db9-9c17-6bb2e733da61")


def load_chunks_jsonl(path: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at line {line_no}: {exc}") from exc
            chunks.append(chunk)
    return chunks


def load_embeddings(path: Path) -> np.ndarray:
    embeddings = np.load(path)
    if not isinstance(embeddings, np.ndarray):
        raise ValueError("embeddings file did not load as a numpy array")
    return embeddings


def load_ids(path: Path) -> np.ndarray:
    ids = np.load(path, allow_pickle=True)
    if not isinstance(ids, np.ndarray):
        raise ValueError("ids file did not load as a numpy array")
    return ids


def chunk_id_to_point_id(chunk_id: str) -> str:
    if not str(chunk_id):
        raise ValueError("chunk_id must not be empty")
    return str(uuid.uuid5(POINT_ID_NAMESPACE, str(chunk_id)))


def validate_qdrant_inputs(
    chunks: Sequence[dict[str, Any]],
    embeddings: np.ndarray,
    ids: Sequence[Any],
    vector_size: int = DEFAULT_VECTOR_SIZE,
) -> None:
    if embeddings.ndim != 2:
        raise ValueError(f"embeddings must be a 2D array, got ndim={embeddings.ndim}")
    if embeddings.shape[1] != vector_size:
        raise ValueError(
            f"embedding vector dimension mismatch: expected {vector_size}, got {embeddings.shape[1]}"
        )
    if len(chunks) != embeddings.shape[0] or len(chunks) != len(ids):
        raise ValueError(
            "count mismatch: "
            f"chunks={len(chunks)}, embeddings_rows={embeddings.shape[0]}, ids={len(ids)}"
        )

    id_strings = [str(chunk_id) for chunk_id in ids]
    if len(set(id_strings)) != len(id_strings):
        raise ValueError("duplicate ids detected")

    chunk_ids = [str(chunk.get("chunk_id", "")) for chunk in chunks]
    if len(set(chunk_ids)) != len(chunk_ids):
        raise ValueError("duplicate chunk_id detected")
    if set(chunk_ids) != set(id_strings):
        raise ValueError("chunk_id set does not match ids set")

    for chunk_id, chunk in zip(id_strings, chunks):
        if str(chunk.get("chunk_id", "")) != chunk_id:
            raise ValueError(f"chunk order mismatch for id {chunk_id}")
        _validate_chunk(chunk)

    if not np.isfinite(embeddings).all():
        raise ValueError("embeddings contain NaN or inf")


def build_payload(chunk: dict[str, Any]) -> dict[str, Any]:
    _validate_chunk(chunk)
    metadata = chunk["metadata"]
    payload = {field: metadata.get(field) for field in sorted(REQUIRED_METADATA_FIELDS)}
    payload["text"] = str(chunk["embedding_text"])
    return payload


def build_point(
    chunk: dict[str, Any],
    vector: np.ndarray | Sequence[float],
    point_id: str | None = None,
) -> PointStruct:
    vector_array = np.asarray(vector, dtype=np.float32)
    if vector_array.ndim != 1:
        raise ValueError(f"point vector must be 1D, got ndim={vector_array.ndim}")
    if vector_array.shape[0] != DEFAULT_VECTOR_SIZE:
        raise ValueError(
            f"point vector dimension mismatch: expected {DEFAULT_VECTOR_SIZE}, got {vector_array.shape[0]}"
        )
    if not np.isfinite(vector_array).all():
        raise ValueError("point vector contains NaN or inf")

    chunk_id = str(chunk["chunk_id"])
    return PointStruct(
        id=point_id or chunk_id_to_point_id(chunk_id),
        vector=vector_array.tolist(),
        payload=build_payload(chunk),
    )


def iter_batches(items: Sequence[Any], batch_size: int) -> Iterable[list[Any]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    for start in range(0, len(items), batch_size):
        yield list(items[start : start + batch_size])


def build_points(
    chunks: Sequence[dict[str, Any]],
    embeddings: np.ndarray,
    ids: Sequence[Any],
    limit: int | None = None,
) -> list[PointStruct]:
    chunk_by_id = {str(chunk.get("chunk_id", "")): chunk for chunk in chunks}
    ordered_ids = [str(chunk_id) for chunk_id in ids]
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        ordered_ids = ordered_ids[:limit]
        embeddings = embeddings[:limit]

    ordered_chunks = [chunk_by_id.get(chunk_id) for chunk_id in ordered_ids]
    if any(chunk is None for chunk in ordered_chunks):
        raise ValueError("ids contain chunk_id values that are missing from chunks")

    validate_qdrant_inputs(ordered_chunks, embeddings, ordered_ids)
    return [build_point(chunk, embeddings[index]) for index, chunk in enumerate(ordered_chunks)]


def summarize_inputs(
    chunks: Sequence[dict[str, Any]],
    embeddings: np.ndarray,
    ids: Sequence[Any],
) -> dict[str, Any]:
    id_strings = [str(chunk_id) for chunk_id in ids]
    return {
        "chunks_count": len(chunks),
        "embeddings_shape": tuple(embeddings.shape),
        "ids_count": len(ids),
        "unique_ids_count": len(set(id_strings)),
        "chunk_ids_count": len({str(chunk.get("chunk_id", "")) for chunk in chunks}),
    }


def ensure_collection_for_load(
    client: Any,
    collection_name: str,
    vector_size: int,
    recreate: bool = False,
    execute: bool = False,
) -> str:
    if not execute:
        raise RuntimeError("Refusing to create or modify Qdrant collection without --execute")

    exists = client.collection_exists(collection_name=collection_name)
    if exists and not recreate:
        raise RuntimeError(f"collection {collection_name} already exists; pass --recreate to replace it")
    if exists and recreate:
        client.delete_collection(collection_name=collection_name)

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    return "created"


def upsert_points(
    client: Any,
    collection_name: str,
    points: Sequence[PointStruct],
    batch_size: int,
) -> int:
    total_batches = 0
    for batch in iter_batches(points, batch_size):
        client.upsert(collection_name=collection_name, points=batch)
        total_batches += 1
    return total_batches


def _validate_chunk(chunk: dict[str, Any]) -> None:
    chunk_id = str(chunk.get("chunk_id", ""))
    if not chunk_id:
        raise ValueError("chunk is missing chunk_id")

    text = chunk.get("embedding_text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"chunk {chunk_id} has empty embedding_text")

    metadata = chunk.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError(f"chunk {chunk_id} is missing metadata")
    missing = REQUIRED_METADATA_FIELDS - set(metadata)
    if missing:
        raise ValueError(f"chunk {chunk_id} metadata missing required fields: {sorted(missing)}")
    if str(metadata.get("chunk_id", "")) != chunk_id:
        raise ValueError(f"chunk {chunk_id} metadata chunk_id mismatch")
