import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import rag_qdrant


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "load_qdrant_phase2.py"
spec = importlib.util.spec_from_file_location("load_qdrant_phase2", SCRIPT_PATH)
load_qdrant_phase2 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(load_qdrant_phase2)


def _metadata(chunk_id: str) -> dict:
    article_id, chunk_index = chunk_id.split(":")
    return {
        "article_id": int(article_id),
        "chunk_id": chunk_id,
        "chunk_index": int(chunk_index),
        "posted_at": "2026.05.18.",
        "created_at": "2026.05.18.",
        "collected_at": "2026-05-18T09:00:00+09:00",
        "year": 2026,
        "month": 5,
        "title": "title",
        "body_len": 4,
        "author": "author",
        "source": "naver_cafe_119investment_goodmorning",
        "url": f"https://example.test/articles/{article_id}",
        "source_url": f"https://example.test/articles/{article_id}",
        "content_hash": f"hash-{article_id}",
        "status": "BODY_COLLECTED",
    }


def _chunk(chunk_id: str, text: str = "body") -> dict:
    article_id, chunk_index = chunk_id.split(":")
    return {
        "chunk_id": chunk_id,
        "article_id": int(article_id),
        "chunk_index": int(chunk_index),
        "embedding_text": text,
        "metadata": _metadata(chunk_id),
    }


def _embeddings(count: int, vector_size: int = rag_qdrant.DEFAULT_VECTOR_SIZE) -> np.ndarray:
    return np.ones((count, vector_size), dtype=np.float32)


class _FakeQdrantClient:
    def __init__(self, exists: bool):
        self.exists = exists
        self.collection_exists_calls = 0
        self.delete_collection_calls = 0
        self.create_collection_calls = 0
        self.created_vector_size = None
        self.created_distance = None

    def collection_exists(self, collection_name: str) -> bool:
        self.collection_exists_calls += 1
        return self.exists

    def delete_collection(self, collection_name: str) -> None:
        self.delete_collection_calls += 1

    def create_collection(self, collection_name: str, vectors_config) -> None:
        self.create_collection_calls += 1
        self.created_vector_size = vectors_config.size
        self.created_distance = vectors_config.distance


def test_valid_sample_input_validation_success():
    chunks = [_chunk("1:0"), _chunk("2:0")]
    embeddings = _embeddings(2)
    ids = np.array(["1:0", "2:0"])

    rag_qdrant.validate_qdrant_inputs(chunks, embeddings, ids)


def test_count_mismatch_detected():
    with pytest.raises(ValueError, match="count mismatch"):
        rag_qdrant.validate_qdrant_inputs([_chunk("1:0")], _embeddings(2), np.array(["1:0", "2:0"]))


def test_vector_dimension_mismatch_detected():
    with pytest.raises(ValueError, match="dimension mismatch"):
        rag_qdrant.validate_qdrant_inputs([_chunk("1:0")], _embeddings(1, 3), np.array(["1:0"]))


def test_duplicate_ids_detected():
    with pytest.raises(ValueError, match="duplicate ids"):
        rag_qdrant.validate_qdrant_inputs(
            [_chunk("1:0"), _chunk("2:0")],
            _embeddings(2),
            np.array(["1:0", "1:0"]),
        )


def test_chunk_id_set_mismatch_detected():
    with pytest.raises(ValueError, match="chunk_id set"):
        rag_qdrant.validate_qdrant_inputs([_chunk("1:0")], _embeddings(1), np.array(["2:0"]))


def test_required_metadata_missing_detected():
    chunk = _chunk("1:0")
    del chunk["metadata"]["author"]

    with pytest.raises(ValueError, match="metadata missing required fields"):
        rag_qdrant.validate_qdrant_inputs([chunk], _embeddings(1), np.array(["1:0"]))


def test_empty_text_detected():
    with pytest.raises(ValueError, match="empty embedding_text"):
        rag_qdrant.validate_qdrant_inputs([_chunk("1:0", "  ")], _embeddings(1), np.array(["1:0"]))


def test_nan_inf_vector_detected():
    embeddings = _embeddings(1)
    embeddings[0, 0] = np.nan

    with pytest.raises(ValueError, match="NaN or inf"):
        rag_qdrant.validate_qdrant_inputs([_chunk("1:0")], embeddings, np.array(["1:0"]))


def test_build_payload_maps_embedding_text_to_text():
    payload = rag_qdrant.build_payload(_chunk("1:0", "hello"))

    assert payload["chunk_id"] == "1:0"
    assert payload["article_id"] == 1
    assert payload["content_hash"] == "hash-1"
    assert payload["url"] == "https://example.test/articles/1"
    assert payload["source_url"] == "https://example.test/articles/1"
    assert payload["created_at"] == "2026.05.18."
    assert payload["collected_at"] == "2026-05-18T09:00:00+09:00"
    assert payload["source"] == "naver_cafe_119investment_goodmorning"
    assert payload["title"] == "title"
    assert payload["text"] == "hello"
    assert "embedding_text" not in payload


def test_chunk_id_to_point_id_is_deterministic_uuid():
    first = rag_qdrant.chunk_id_to_point_id("1:0")
    second = rag_qdrant.chunk_id_to_point_id("1:0")
    other = rag_qdrant.chunk_id_to_point_id("1:1")

    assert first == second
    assert first != other
    assert len(first) == 36


def test_build_points_uses_ids_order_for_chunk_matching():
    chunks = [_chunk("2:0", "second"), _chunk("1:0", "first")]
    embeddings = _embeddings(2)
    embeddings[0, 0] = 10.0
    embeddings[1, 0] = 20.0
    ids = np.array(["1:0", "2:0"])

    points = rag_qdrant.build_points(chunks, embeddings, ids)

    assert points[0].payload["chunk_id"] == "1:0"
    assert points[0].payload["text"] == "first"
    assert points[0].vector[0] == 10.0
    assert points[1].payload["chunk_id"] == "2:0"
    assert points[1].vector[0] == 20.0


def test_iter_batches():
    batches = list(rag_qdrant.iter_batches([1, 2, 3, 4, 5], 2))

    assert batches == [[1, 2], [3, 4], [5]]


def test_dry_run_does_not_create_qdrant_storage(tmp_path, monkeypatch):
    chunks_path = tmp_path / "chunks.jsonl"
    embeddings_path = tmp_path / "embeddings.npy"
    ids_path = tmp_path / "ids.npy"
    qdrant_path = tmp_path / "qdrant"
    chunks_path.write_text(json.dumps(_chunk("1:0"), ensure_ascii=False) + "\n", encoding="utf-8")
    np.save(embeddings_path, _embeddings(1))
    np.save(ids_path, np.array(["1:0"]))

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "load_qdrant_phase2.py",
            "--chunks-path",
            str(chunks_path),
            "--embeddings-path",
            str(embeddings_path),
            "--ids-path",
            str(ids_path),
            "--qdrant-path",
            str(qdrant_path),
            "--dry-run",
        ],
    )

    assert load_qdrant_phase2.main() == 0
    assert not qdrant_path.exists()


def test_existing_collection_without_recreate_fails_without_delete_or_create():
    client = _FakeQdrantClient(exists=True)

    with pytest.raises(RuntimeError, match="already exists"):
        rag_qdrant.ensure_collection_for_load(
            client,
            collection_name="goodmorning_chunks",
            vector_size=rag_qdrant.DEFAULT_VECTOR_SIZE,
            recreate=False,
            execute=True,
        )

    assert client.collection_exists_calls == 1
    assert client.delete_collection_calls == 0
    assert client.create_collection_calls == 0


def test_recreate_without_execute_fails_without_delete_or_create():
    client = _FakeQdrantClient(exists=True)

    with pytest.raises(RuntimeError, match="without --execute"):
        rag_qdrant.ensure_collection_for_load(
            client,
            collection_name="goodmorning_chunks",
            vector_size=rag_qdrant.DEFAULT_VECTOR_SIZE,
            recreate=True,
            execute=False,
        )

    assert client.collection_exists_calls == 0
    assert client.delete_collection_calls == 0
    assert client.create_collection_calls == 0


def test_recreate_with_execute_deletes_then_creates():
    client = _FakeQdrantClient(exists=True)

    result = rag_qdrant.ensure_collection_for_load(
        client,
        collection_name="goodmorning_chunks",
        vector_size=rag_qdrant.DEFAULT_VECTOR_SIZE,
        recreate=True,
        execute=True,
    )

    assert result == "created"
    assert client.collection_exists_calls == 1
    assert client.delete_collection_calls == 1
    assert client.create_collection_calls == 1
    assert client.created_vector_size == rag_qdrant.DEFAULT_VECTOR_SIZE
    assert str(client.created_distance).lower().endswith("cosine")


def test_missing_collection_with_execute_creates_only():
    client = _FakeQdrantClient(exists=False)

    result = rag_qdrant.ensure_collection_for_load(
        client,
        collection_name="goodmorning_chunks",
        vector_size=rag_qdrant.DEFAULT_VECTOR_SIZE,
        recreate=False,
        execute=True,
    )

    assert result == "created"
    assert client.collection_exists_calls == 1
    assert client.delete_collection_calls == 0
    assert client.create_collection_calls == 1
    assert client.created_vector_size == rag_qdrant.DEFAULT_VECTOR_SIZE
    assert str(client.created_distance).lower().endswith("cosine")


def test_cli_dry_run_and_execute_are_mutually_exclusive(tmp_path):
    chunks_path = tmp_path / "chunks.jsonl"
    embeddings_path = tmp_path / "embeddings.npy"
    ids_path = tmp_path / "ids.npy"
    qdrant_path = tmp_path / "qdrant"
    chunks_path.write_text(json.dumps(_chunk("1:0"), ensure_ascii=False) + "\n", encoding="utf-8")
    np.save(embeddings_path, _embeddings(1))
    np.save(ids_path, np.array(["1:0"]))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--chunks-path",
            str(chunks_path),
            "--embeddings-path",
            str(embeddings_path),
            "--ids-path",
            str(ids_path),
            "--qdrant-path",
            str(qdrant_path),
            "--dry-run",
            "--execute",
            "--limit",
            "1",
        ],
        cwd=SCRIPT_PATH.parent.parent,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "mutually exclusive" in result.stderr
    assert not qdrant_path.exists()
