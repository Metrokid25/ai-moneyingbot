import importlib.util
import json
from pathlib import Path

import numpy as np


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "embed_chunks_phase2.py"
spec = importlib.util.spec_from_file_location("embed_chunks_phase2", SCRIPT_PATH)
embed_chunks_phase2 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(embed_chunks_phase2)


def _write_chunks(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _chunk(chunk_id: str, text: str = "본문") -> dict:
    return {
        "chunk_id": chunk_id,
        "article_id": int(chunk_id.split(":")[0]),
        "chunk_index": int(chunk_id.split(":")[1]),
        "embedding_text": text,
        "metadata": {"chunk_id": chunk_id},
    }


def test_read_chunks_parses_chunk_id_and_embedding_text(tmp_path):
    path = tmp_path / "chunks.jsonl"
    _write_chunks(path, [_chunk("1:0", "hello")])

    chunks, stats = embed_chunks_phase2.read_chunks(path)

    assert chunks == [{"chunk_id": "1:0", "embedding_text": "hello"}]
    assert stats["bad_json_count"] == 0


def test_duplicate_chunk_id_detected(tmp_path):
    path = tmp_path / "chunks.jsonl"
    _write_chunks(path, [_chunk("1:0"), _chunk("1:0")])

    _chunks, stats = embed_chunks_phase2.read_chunks(path)

    assert stats["duplicate_chunk_ids"] == 1


def test_empty_embedding_text_detected(tmp_path):
    path = tmp_path / "chunks.jsonl"
    _write_chunks(path, [_chunk("1:0", "   ")])

    _chunks, stats = embed_chunks_phase2.read_chunks(path)

    assert stats["empty_embedding_text_count"] == 1


def test_limit_applied():
    chunks = [_chunk(f"{i}:0") for i in range(5)]

    selected, already_done = embed_chunks_phase2.select_chunks(
        chunks,
        limit=2,
        resume=False,
        done_chunk_ids=set(),
    )

    assert [c["chunk_id"] for c in selected] == ["0:0", "1:0"]
    assert already_done == 0


def test_resume_progress_skip_calculated(tmp_path):
    progress = tmp_path / "progress.jsonl"
    progress.write_text(
        json.dumps({"chunk_id": "1:0", "index": 0, "status": "OK", "model": "voyage-3-large"})
        + "\n",
        encoding="utf-8",
    )
    done = embed_chunks_phase2.read_done_chunk_ids(progress)
    chunks = [_chunk("1:0"), _chunk("2:0")]

    selected, already_done = embed_chunks_phase2.select_chunks(
        chunks,
        limit=None,
        resume=True,
        done_chunk_ids=done,
    )

    assert already_done == 1
    assert [c["chunk_id"] for c in selected] == ["2:0"]


def test_mock_vector_shape_is_1024():
    vector = embed_chunks_phase2.mock_embedding("169913:0")

    assert vector.shape == (1024,)
    assert vector.dtype == np.float32


def test_mock_ids_and_embeddings_count_match(tmp_path):
    chunks = [_chunk("1:0"), _chunk("2:0")]
    out_embeddings = tmp_path / "emb.npy"
    out_ids = tmp_path / "ids.npy"
    progress = tmp_path / "progress.jsonl"

    shape, ids_count = embed_chunks_phase2.write_mock_outputs(
        chunks,
        out_embeddings=out_embeddings,
        out_ids=out_ids,
        progress_path=progress,
        model="voyage-3-large",
        overwrite=False,
    )

    embeddings = np.load(out_embeddings)
    ids = np.load(out_ids)
    assert shape == (2, 1024)
    assert ids_count == 2
    assert embeddings.shape == (2, 1024)
    assert len(ids) == 2
    assert progress.read_text(encoding="utf-8").count("\n") == 2


def test_dry_run_does_not_create_files(tmp_path):
    path = tmp_path / "chunks.jsonl"
    _write_chunks(path, [_chunk("1:0")])
    out_embeddings = tmp_path / "emb.npy"
    out_ids = tmp_path / "ids.npy"
    progress = tmp_path / "progress.jsonl"

    chunks, stats = embed_chunks_phase2.read_chunks(path)
    selected, already_done = embed_chunks_phase2.select_chunks(
        chunks,
        limit=1,
        resume=False,
        done_chunk_ids=set(),
    )
    summary = embed_chunks_phase2.build_summary(
        args=type(
            "Args",
            (),
            {
                "batch_size": 128,
                "model": "voyage-3-large",
                "resume": False,
                "dry_run": True,
                "mock": False,
                "execute": False,
            },
        )(),
        chunks_path=path,
        out_embeddings=out_embeddings,
        out_ids=out_ids,
        progress_path=progress,
        total_chunks=len(chunks),
        selected_chunks=len(selected),
        stats=stats,
        already_done_count=already_done,
    )

    assert summary["dry_run"] is True
    assert not out_embeddings.exists()
    assert not out_ids.exists()
    assert not progress.exists()
