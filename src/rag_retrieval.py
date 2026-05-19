import os
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from dotenv import load_dotenv
from qdrant_client import QdrantClient


DEFAULT_QDRANT_PATH = "data/qdrant"
DEFAULT_COLLECTION = "goodmorning_chunks"
DEFAULT_MODEL = "voyage-3-large"
DEFAULT_TOP_K = 5
VECTOR_SIZE = 1024
MAX_TOP_K = 20
SNIPPET_CHARS = 250


def validate_run_mode(dry_run: bool, execute: bool) -> None:
    if dry_run and execute:
        raise ValueError("--dry-run and --execute are mutually exclusive.")
    if not dry_run and not execute:
        raise ValueError("Refusing to call Voyage API or search Qdrant without --execute.")


def validate_top_k(top_k: int) -> None:
    if not (1 <= top_k <= MAX_TOP_K):
        raise ValueError(f"--top-k must be between 1 and {MAX_TOP_K}")


def make_snippet(text: str | None, max_chars: int = SNIPPET_CHARS) -> str:
    if not text:
        return ""
    normalized = " ".join(str(text).split())
    return normalized[:max_chars]


def validate_query_vector(vector: Sequence[float], vector_size: int = VECTOR_SIZE) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float32)
    if array.ndim != 1:
        raise ValueError(f"query vector must be 1D, got ndim={array.ndim}")
    if array.shape[0] != vector_size:
        raise ValueError(f"query vector dimension mismatch: expected {vector_size}, got {array.shape[0]}")
    if not np.isfinite(array).all():
        raise ValueError("query vector contains NaN or inf")
    return array


def load_voyage_api_key(project_root: Path | None = None) -> str:
    if project_root is not None:
        load_dotenv(project_root / ".env")
    else:
        load_dotenv()
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY is required for --execute")
    return api_key


def embed_query(query: str, model: str = DEFAULT_MODEL, project_root: Path | None = None) -> np.ndarray:
    if not query.strip():
        raise ValueError("--query must not be empty")
    load_voyage_api_key(project_root)

    import voyageai

    client = voyageai.Client()
    result = client.embed(texts=[query], model=model, input_type="query")
    if not result.embeddings:
        raise RuntimeError("Voyage returned no query embedding")
    return validate_query_vector(result.embeddings[0])


def open_qdrant_client(qdrant_path: Path | str) -> QdrantClient:
    return QdrantClient(path=str(qdrant_path))


def get_collection_summary(client: QdrantClient, collection: str) -> dict[str, Any]:
    exists = client.collection_exists(collection_name=collection)
    summary: dict[str, Any] = {"collection_exists": exists}
    if not exists:
        return summary

    info = client.get_collection(collection_name=collection)
    vectors_config = info.config.params.vectors
    summary.update(
        {
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": info.status,
            "vector_size": vectors_config.size,
            "distance": vectors_config.distance,
        }
    )
    return summary


def ensure_collection_exists(client: QdrantClient, collection: str) -> None:
    if not client.collection_exists(collection_name=collection):
        raise RuntimeError(f"collection {collection} does not exist")


def search_qdrant(
    client: QdrantClient,
    collection: str,
    query_vector: Sequence[float],
    top_k: int = DEFAULT_TOP_K,
):
    validate_top_k(top_k)
    vector = validate_query_vector(query_vector)
    ensure_collection_exists(client, collection)
    return client.search(
        collection_name=collection,
        query_vector=vector.tolist(),
        limit=top_k,
        with_payload=True,
        with_vectors=False,
    )


def format_search_result(point: Any, rank: int) -> dict[str, Any]:
    payload = point.payload or {}
    return {
        "rank": rank,
        "score": point.score,
        "chunk_id": payload.get("chunk_id"),
        "article_id": payload.get("article_id"),
        "posted_at": payload.get("posted_at"),
        "title": payload.get("title"),
        "snippet": make_snippet(payload.get("text")),
        "source": payload.get("source"),
    }


def format_search_results(points: Sequence[Any]) -> list[dict[str, Any]]:
    return [format_search_result(point, rank=index + 1) for index, point in enumerate(points)]
