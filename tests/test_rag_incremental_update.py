import importlib.util
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "update_rag_index_incremental.py"

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


inc = _load("update_rag_index_incremental", SCRIPT)


ARTICLES_SCHEMA = """
CREATE TABLE articles (
    article_id INTEGER, title TEXT, url TEXT, author TEXT, posted_at TEXT,
    raw_html TEXT, clean_text TEXT, source_page INTEGER, status TEXT,
    error_reason TEXT, saved_at TEXT, updated_at TEXT, attempt_count INTEGER,
    last_error_reason TEXT, last_attempt_at TEXT
)
"""


def _row(i: int, body: str):
    return {
        "article_id": i,
        "title": f"제목 {i}",
        "url": f"https://cafe.naver.com/x/{i}",
        "author": "글쓴이",
        "posted_at": "2026-01-02",
        "clean_text": body,
        "saved_at": "2026-01-03",
        "updated_at": "2026-01-03",
        "status": "BODY_COLLECTED",
    }


def _make_db(path: Path, rows: list[dict]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(ARTICLES_SCHEMA)
        for r in rows:
            conn.execute(
                "INSERT INTO articles (article_id, title, url, author, posted_at, clean_text, saved_at, updated_at, status) "
                "VALUES (:article_id, :title, :url, :author, :posted_at, :clean_text, :saved_at, :updated_at, :status)",
                r,
            )
        conn.commit()
    finally:
        conn.close()


def test_collect_current_chunks_from_db(tmp_path):
    db = tmp_path / "archive.db"
    _make_db(db, [_row(1, "첫 본문입니다."), _row(2, "둘째 본문입니다.")])
    chunks = inc.collect_current_chunks(db)
    assert len(chunks) >= 2
    assert all("chunk_id" in c and "embedding_text" in c for c in chunks)


def test_select_new_chunks_excludes_indexed():
    chunks = [{"chunk_id": "1:0"}, {"chunk_id": "2:0"}, {"chunk_id": "3:0"}]
    new = inc.select_new_chunks(chunks, {"1:0", "2:0"})
    assert [c["chunk_id"] for c in new] == ["3:0"]


def test_select_new_chunks_empty_when_all_indexed():
    chunks = [{"chunk_id": "1:0"}, {"chunk_id": "2:0"}]
    assert inc.select_new_chunks(chunks, {"1:0", "2:0"}) == []


def test_manifest_round_trip(tmp_path):
    man = tmp_path / "manifest.jsonl"
    inc.append_manifest(man, ["1:0", "2:0"])
    inc.append_manifest(man, ["3:0"])
    assert inc.load_manifest(man) == {"1:0", "2:0", "3:0"}


def test_load_manifest_empty_when_no_manifest_or_seed(tmp_path):
    assert inc.load_manifest(tmp_path / "none.jsonl", tmp_path / "noseed.npy") == set()


def test_manifest_after_update_merges_seed_and_new():
    # Full indexed set after upsert = seed baseline + new ids (sorted, deduped).
    result = inc.manifest_after_update({"1:0", "2:0"}, ["3:0", "2:0"])
    assert result == ["1:0", "2:0", "3:0"]


def test_write_manifest_overwrites_with_full_set(tmp_path):
    man = tmp_path / "manifest.jsonl"
    inc.append_manifest(man, ["old:0"])  # stale partial content
    inc.write_manifest(man, ["1:0", "2:0", "3:0"])  # overwrite with full set
    assert inc.load_manifest(man) == {"1:0", "2:0", "3:0"}


def test_first_run_persists_full_baseline_not_just_delta(tmp_path):
    # Regression: first execute must persist seed+new, so the NEXT run's baseline
    # is the full set (not only the delta) -> next run does not re-index everything.
    indexed = {f"{i}:0" for i in range(50)}  # pretend 50 already indexed (seed)
    new_ids = ["50:0", "51:0"]
    man = tmp_path / "manifest.jsonl"
    inc.write_manifest(man, inc.manifest_after_update(indexed, new_ids))
    assert inc.load_manifest(man) == indexed | {"50:0", "51:0"}
    assert len(inc.load_manifest(man)) == 52


def test_dry_run_main_detects_new_without_side_effects(tmp_path, capsys):
    db = tmp_path / "archive.db"
    _make_db(db, [_row(1, "본문 하나."), _row(2, "본문 둘.")])
    man = tmp_path / "manifest.jsonl"  # absent -> empty -> all chunks are new
    rc = inc.main([
        "--db-path", str(db),
        "--manifest-path", str(man),
        "--seed-ids-path", str(tmp_path / "noseed.npy"),
        "--dry-run",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"new_chunks"' in out
    assert '"dry_run": true' in out
    # dry-run must not create the manifest
    assert not man.exists()


def test_execute_with_zero_new_is_noop(tmp_path, capsys):
    # Seed manifest with all chunk_ids first so execute finds nothing new and
    # never calls the embed/upsert path (no API/qdrant needed).
    db = tmp_path / "archive.db"
    _make_db(db, [_row(1, "본문 하나."), _row(2, "본문 둘.")])
    chunks = inc.collect_current_chunks(db)
    man = tmp_path / "manifest.jsonl"
    inc.append_manifest(man, [str(c["chunk_id"]) for c in chunks])
    rc = inc.main([
        "--db-path", str(db),
        "--manifest-path", str(man),
        "--seed-ids-path", str(tmp_path / "noseed.npy"),
        "--execute",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"new_chunks": 0' in out
    assert "already current" in out


def test_requires_a_run_mode(tmp_path):
    db = tmp_path / "archive.db"
    _make_db(db, [_row(1, "본문.")])
    rc = inc.main(["--db-path", str(db)])
    assert rc == 2
