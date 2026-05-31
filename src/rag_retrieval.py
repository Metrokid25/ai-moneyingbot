import json
import os
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from dotenv import load_dotenv

try:
    from qdrant_client import QdrantClient
except ModuleNotFoundError:
    QdrantClient = None


DEFAULT_QDRANT_PATH = "data/qdrant"
DEFAULT_COLLECTION = "goodmorning_chunks"
DEFAULT_MODEL = "voyage-3-large"
DEFAULT_TOP_K = 5
VECTOR_SIZE = 1024
MAX_TOP_K = 20
SNIPPET_CHARS = 250
SOURCE_METADATA_FIELDS = (
    "article_id",
    "source_id",
    "source_path",
    "content_hash",
    "url",
    "source_url",
    "created_at",
    "collected_at",
    "posted_at",
    "source",
    "title",
    "chunk_id",
)
EVALUATION_QUERIES = [
    "금리 인상 국면에서 주식시장은 어떻게 반응하는가",
    "원달러 환율 상승이 외국인 수급에 미치는 영향",
    "외국인 매수와 매도가 코스피에 미치는 영향",
    "반도체 업황과 삼성전자 주가 전망",
    "코스피 지수 흐름과 시장 방향성",
    "경기침체 우려와 경기회복 신호",
    "인플레이션과 물가 상승이 증시에 주는 부담",
    "유가와 원자재 가격 상승이 시장에 미치는 영향",
    "부동산 시장과 금리 상승의 관계",
    "미국 증시 흐름이 한국 증시에 미치는 영향",
    "중국 경제 둔화와 한국 주식시장 영향",
    "채권시장과 국채금리 상승의 의미",
    "개인투자자 심리와 시장 과열 신호",
    "신용매수와 레버리지 투자 위험",
    "기업 실적과 기업이익 전망이 주가에 미치는 영향",
]


def validate_run_mode(dry_run: bool, execute: bool) -> None:
    if dry_run and execute:
        raise ValueError("--dry-run and --execute are mutually exclusive.")
    if not dry_run and not execute:
        raise ValueError("Refusing to call Voyage API or search Qdrant without --execute.")


def validate_top_k(top_k: int) -> None:
    if not (1 <= top_k <= MAX_TOP_K):
        raise ValueError(f"--top-k must be between 1 and {MAX_TOP_K}")


def validate_score_threshold(score_threshold: float | None) -> None:
    if score_threshold is None:
        return
    if not np.isfinite(float(score_threshold)):
        raise ValueError("score_threshold must be a finite number")


def make_snippet(text: str | None, max_chars: int = SNIPPET_CHARS) -> str:
    if not text:
        return ""
    normalized = " ".join(str(text).split())
    return normalized[:max_chars]


def payload_value(payload: dict[str, Any], field: str) -> Any:
    if field in payload:
        return payload.get(field)
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        return metadata.get(field)
    return None


def extract_source_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {field: payload_value(payload, field) for field in SOURCE_METADATA_FIELDS}


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
    if QdrantClient is None:
        raise RuntimeError("qdrant_client is required for Qdrant search")
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
    score_threshold: float | None = None,
):
    validate_top_k(top_k)
    validate_score_threshold(score_threshold)
    vector = validate_query_vector(query_vector)
    ensure_collection_exists(client, collection)
    return client.search(
        collection_name=collection,
        query_vector=vector.tolist(),
        limit=top_k,
        score_threshold=score_threshold,
        with_payload=True,
        with_vectors=False,
    )


def format_search_result(point: Any, rank: int) -> dict[str, Any]:
    payload = point.payload or {}
    row = {
        "rank": rank,
        "score": point.score,
        **extract_source_metadata(payload),
        "snippet": make_snippet(payload.get("text")),
    }
    return row


def format_search_results(
    points: Sequence[Any],
    score_threshold: float | None = None,
) -> list[dict[str, Any]]:
    validate_score_threshold(score_threshold)
    rows = []
    for point in points:
        if score_threshold is not None and float(point.score) < score_threshold:
            continue
        rows.append(format_search_result(point, rank=len(rows) + 1))
    return rows


def validate_eval_queries(queries: Sequence[str]) -> None:
    if not queries:
        raise ValueError("evaluation queries must not be empty")
    normalized = [query.strip() for query in queries]
    if any(not query for query in normalized):
        raise ValueError("evaluation queries must not contain empty values")
    if len(set(normalized)) != len(normalized):
        raise ValueError("evaluation queries must not contain duplicates")


def format_eval_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": result.get("rank"),
        "score": result.get("score"),
        "chunk_id": result.get("chunk_id"),
        "article_id": result.get("article_id"),
        "posted_at": result.get("posted_at"),
        "title": result.get("title"),
        "snippet": make_snippet(result.get("snippet")),
        "source": result.get("source"),
    }


def build_eval_record(query: str, results: Sequence[dict[str, Any]], top_k: int = DEFAULT_TOP_K) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query must not be empty")
    validate_top_k(top_k)
    return {
        "query": query,
        "top_k": top_k,
        "results": [format_eval_result(result) for result in results],
    }


def validate_output_path(out_path: Path, overwrite: bool, execute: bool) -> None:
    if overwrite and not execute:
        raise ValueError("--overwrite requires --execute")
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"{out_path} already exists; pass --overwrite to replace it")


def write_jsonl(path: Path, records: Sequence[dict[str, Any]], overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
