import importlib.util
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXPORT_SCRIPT = ROOT / "scripts" / "export_archive_articles.py"
INGEST_SCRIPT = ROOT / "scripts" / "ingest_archive_export.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


export_mod = _load("export_archive_articles", EXPORT_SCRIPT)
ingest_mod = _load("ingest_archive_export", INGEST_SCRIPT)


ARTICLES_SCHEMA = """
CREATE TABLE articles (
    article_id INTEGER,
    title TEXT,
    url TEXT,
    author TEXT,
    posted_at TEXT,
    raw_html TEXT,
    clean_text TEXT,
    source_page INTEGER,
    status TEXT,
    error_reason TEXT,
    saved_at TEXT,
    updated_at TEXT,
    attempt_count INTEGER,
    last_error_reason TEXT,
    last_attempt_at TEXT
)
"""


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


def _row(**overrides):
    base = {
        "article_id": 1,
        "title": "제목",
        "url": "https://cafe.naver.com/x/1",
        "author": "글쓴이",
        "posted_at": "2026-01-02",
        "clean_text": "본문 내용입니다.",
        "saved_at": "2026-01-03",
        "updated_at": "2026-01-03",
        "status": "BODY_COLLECTED",
    }
    base.update(overrides)
    return base


def test_export_record_has_all_required_fields_non_empty():
    record = export_mod.build_export_record(_row())
    assert record is not None
    for field in export_mod.EXPORT_FIELDS:
        value = record[field]
        assert value is not None and str(value).strip() != "", field


def test_export_record_computes_content_hash_from_body():
    record = export_mod.build_export_record(_row(clean_text="hello"))
    assert record["content_hash"] == export_mod.content_hash_for("hello")
    assert record["body_text"] == "hello"
    assert record["source"] == export_mod.DEFAULT_SOURCE


def test_export_skips_incomplete_rows():
    assert export_mod.build_export_record(_row(clean_text="")) is None
    assert export_mod.build_export_record(_row(url="  ")) is None
    assert export_mod.build_export_record(_row(title="")) is None
    assert export_mod.build_export_record(_row(posted_at="", saved_at="")) is None


def test_collected_at_falls_back_when_saved_at_missing():
    record = export_mod.build_export_record(_row(saved_at="", updated_at="2026-02-02"))
    assert record is not None
    assert record["collected_at"] == "2026-02-02"


def test_export_output_passes_ingest_validation(tmp_path):
    db = tmp_path / "archive.db"
    _make_db(
        db,
        [
            _row(article_id=1, clean_text="첫 번째 본문"),
            _row(article_id=2, clean_text="두 번째 본문", title="두번째"),
            _row(article_id=3, clean_text="", title="빈본문"),  # skipped
        ],
    )
    rows = export_mod.fetch_rows(db)
    records = list(export_mod.iter_export_records(rows))
    assert len(records) == 2  # the empty-body row is skipped

    # Every exported record must satisfy the ingest contract.
    for line_no, record in enumerate(records, start=1):
        ingest_mod.validate_required_fields(record, line_no)
        normalized = ingest_mod.normalize_article(record)
        assert normalized["clean_text"]
        assert normalized["source_url"] == record["url"]


def test_fetch_rows_opens_db_read_only():
    # The script must use a read-only sqlite URI so it can never mutate archive.db.
    script_text = EXPORT_SCRIPT.read_text(encoding="utf-8")
    assert "mode=ro" in script_text
    assert "never writes to" in script_text.lower()
