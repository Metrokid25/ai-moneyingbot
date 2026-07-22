import base64
import json
import pickle
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_rag_deploy_assets as checker  # noqa: E402


def _make_archive_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE articles (article_id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO articles VALUES (1)")
    conn.commit()
    conn.close()


def _make_qdrant(
    path: Path,
    *,
    count: int,
    size: int = 1024,
    distance: str = "Cosine",
    chunk_ids: list[str] | None = None,
) -> None:
    collection = "goodmorning_chunks"
    storage_dir = path / "collection" / collection
    storage_dir.mkdir(parents=True)
    (path / "meta.json").write_text(
        json.dumps(
            {
                "collections": {
                    collection: {"vectors": {"size": size, "distance": distance}}
                },
                "aliases": {},
            }
        ),
        encoding="utf-8",
    )
    conn = sqlite3.connect(storage_dir / "storage.sqlite")
    conn.execute("CREATE TABLE points (id TEXT PRIMARY KEY, point BLOB)")
    source_ids = chunk_ids or [f"{index + 1}:0" for index in range(count)]
    assert len(source_ids) == count
    stored_ids = [
        base64.b64encode(
            pickle.dumps(checker.chunk_id_to_point_id(chunk_id), protocol=4)
        ).decode("ascii")
        for chunk_id in source_ids
    ]
    conn.executemany("INSERT INTO points VALUES (?, ?)", [(point_id, b"x") for point_id in stored_ids])
    conn.commit()
    conn.close()


def _make_manifest(path: Path, ids: list[str]) -> None:
    path.write_text(
        "".join(json.dumps({"chunk_id": chunk_id}) + "\n" for chunk_id in ids),
        encoding="utf-8",
    )


def _paths(tmp_path: Path, *, qdrant_count: int = 2):
    db = tmp_path / "archive.db"
    qdrant = tmp_path / "qdrant"
    manifest = tmp_path / "manifest.jsonl"
    seed = tmp_path / "seed.npy"
    _make_archive_db(db)
    _make_qdrant(qdrant, count=qdrant_count)
    return db, qdrant, manifest, seed


def test_check_assets_passes_matching_manifest_and_qdrant(tmp_path):
    db, qdrant, manifest, seed = _paths(tmp_path)
    _make_manifest(manifest, ["1:0", "2:0"])

    summary = checker.check_assets(
        db_path=db,
        qdrant_path=qdrant,
        manifest_path=manifest,
        seed_ids_path=seed,
        collection="goodmorning_chunks",
    )

    assert summary["status"] == "PASS"
    assert summary["qdrant"]["points_count"] == 2
    assert summary["baseline"]["source"] == "manifest"
    assert summary["baseline"]["unique_ids_count"] == 2
    assert summary["archive_db"]["sqlite_query_only"] is True
    assert summary["write_performed"] is False


def test_check_assets_rejects_qdrant_baseline_count_mismatch(tmp_path):
    db, qdrant, manifest, seed = _paths(tmp_path, qdrant_count=2)
    _make_manifest(manifest, ["1:0"])

    with pytest.raises(checker.AssetCheckError, match="count mismatch"):
        checker.check_assets(
            db_path=db,
            qdrant_path=qdrant,
            manifest_path=manifest,
            seed_ids_path=seed,
            collection="goodmorning_chunks",
        )


def test_check_assets_rejects_same_count_with_different_point_ids(tmp_path):
    db = tmp_path / "archive.db"
    qdrant = tmp_path / "qdrant"
    manifest = tmp_path / "manifest.jsonl"
    seed = tmp_path / "seed.npy"
    _make_archive_db(db)
    _make_qdrant(qdrant, count=2, chunk_ids=["9:0", "10:0"])
    _make_manifest(manifest, ["1:0", "2:0"])

    with pytest.raises(checker.AssetCheckError, match="point ID set mismatch"):
        checker.check_assets(
            db_path=db,
            qdrant_path=qdrant,
            manifest_path=manifest,
            seed_ids_path=seed,
            collection="goodmorning_chunks",
        )


def test_present_corrupt_manifest_does_not_fall_back_to_seed(tmp_path):
    _db, _qdrant, manifest, seed = _paths(tmp_path)
    manifest.write_text("not-json\n", encoding="utf-8")
    np.save(seed, np.asarray(["1:0", "2:0"]))

    with pytest.raises(checker.AssetCheckError, match="invalid manifest JSON"):
        checker.load_baseline_info(manifest, seed)


@pytest.mark.parametrize("bad_chunk_id", [None, 123, [], {}, "bad", "1:-1", "01:0"])
def test_manifest_rejects_non_contract_chunk_ids(tmp_path, bad_chunk_id):
    manifest = tmp_path / "manifest.jsonl"
    seed = tmp_path / "seed.npy"
    manifest.write_text(json.dumps({"chunk_id": bad_chunk_id}) + "\n", encoding="utf-8")

    with pytest.raises(checker.AssetCheckError, match="invalid chunk_id"):
        checker.load_baseline_info(manifest, seed)


def test_check_assets_accepts_seed_when_manifest_is_absent(tmp_path):
    db, qdrant, manifest, seed = _paths(tmp_path)
    np.save(seed, np.asarray(["1:0", "2:0"]))

    summary = checker.check_assets(
        db_path=db,
        qdrant_path=qdrant,
        manifest_path=manifest,
        seed_ids_path=seed,
        collection="goodmorning_chunks",
    )

    assert summary["baseline"]["source"] == "seed"
    assert summary["baseline"]["unique_ids_count"] == 2


def test_check_assets_rejects_wrong_vector_config(tmp_path):
    db = tmp_path / "archive.db"
    qdrant = tmp_path / "qdrant"
    manifest = tmp_path / "manifest.jsonl"
    seed = tmp_path / "seed.npy"
    _make_archive_db(db)
    _make_qdrant(qdrant, count=2, size=768)
    _make_manifest(manifest, ["1:0", "2:0"])

    with pytest.raises(checker.AssetCheckError, match="vector size mismatch"):
        checker.check_assets(
            db_path=db,
            qdrant_path=qdrant,
            manifest_path=manifest,
            seed_ids_path=seed,
            collection="goodmorning_chunks",
        )


def test_main_reports_failure_without_writing(tmp_path, capsys):
    db, qdrant, manifest, seed = _paths(tmp_path, qdrant_count=2)
    _make_manifest(manifest, ["1:0"])

    rc = checker.main(
        [
            "--db-path",
            str(db),
            "--qdrant-path",
            str(qdrant),
            "--manifest-path",
            str(manifest),
            "--seed-ids-path",
            str(seed),
        ]
    )

    assert rc == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "FAIL"
    assert output["write_performed"] is False


def test_schedule_registration_runs_gate_before_registering_task():
    script = (ROOT / "scripts" / "register_rag_index_schedule.ps1").read_text(encoding="utf-8")

    assert "check_rag_deploy_assets.py" in script
    assert script.index("& $python @checkArgs") < script.index("Register-ScheduledTask")
    assert 'throw "RAG deployment asset preflight failed' in script
    assert '"--manifest-path"' in script
    assert '"--seed-ids-path"' in script
