"""tests/test_snapshot.py — 스냅샷 기능 단위 테스트.

_create_snapshot / _load_latest_snapshot / index_pages(snapshot_max_id) /
_collect_after_snapshot 검증.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

import db as db_module
from db import get_conn, init_db, upsert_article, article_exists
from models import Article, Status


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    init_db()


@pytest.fixture()
def snapshot_dir(tmp_path, monkeypatch):
    """index_tail._SNAPSHOT_DIR을 tmp_path로 교체."""
    import index_tail
    monkeypatch.setattr(index_tail, "_SNAPSHOT_DIR", tmp_path)
    return tmp_path


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _make_session(page_rows_map: dict):
    """page_num → rows 매핑을 받아 goto/get_frame_html/parse_article_list를 흉내내는 mock session."""
    session = MagicMock()

    def _goto(url):
        return (url, None)

    def _get_frame_html():
        return ("<html/>", None)

    session.goto.side_effect = _goto
    session.get_frame_html.side_effect = _get_frame_html
    session.page.frame.return_value = MagicMock(name="cafe_main")
    session.page.frames = []
    return session


def _write_snapshot(tmp_path: Path, snapshot_max_id: int, ts: str = "20260501_120000") -> Path:
    data = {"created_at": ts, "snapshot_max_id": snapshot_max_id, "db_max_id_at_snapshot": None}
    path = tmp_path / f"snapshot_{ts}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ── _load_latest_snapshot ─────────────────────────────────────────────────────

def test_load_latest_snapshot_returns_most_recent(snapshot_dir, tmp_path):
    _write_snapshot(tmp_path, snapshot_max_id=500, ts="20260501_100000")
    _write_snapshot(tmp_path, snapshot_max_id=999, ts="20260502_080000")

    import index_tail
    result = index_tail._load_latest_snapshot()

    assert result is not None
    assert result["snapshot_max_id"] == 999


def test_load_latest_snapshot_returns_none_when_empty(snapshot_dir):
    import index_tail
    result = index_tail._load_latest_snapshot()
    assert result is None


# ── index_pages snapshot_max_id 필터 ─────────────────────────────────────────

def test_index_pages_skips_article_ids_above_snapshot(tmp_path):
    """snapshot_max_id=1000 → article_id > 1000인 글은 무시, 이하는 저장."""
    rows_page1 = [
        {"article_id": 1005, "title": "신규글A", "url": "https://cafe.naver.com/a/1005", "posted_at": "2026-05-02"},
        {"article_id": 1003, "title": "신규글B", "url": "https://cafe.naver.com/a/1003", "posted_at": "2026-05-02"},
        {"article_id": 998,  "title": "기존글C", "url": "https://cafe.naver.com/a/998",  "posted_at": "2026-04-01"},
    ]

    session = _make_session({})

    with patch("index_tail.parse_article_list", return_value=rows_page1), \
         patch("index_tail.check_blocked", return_value=None), \
         patch("index_tail._sleep"):
        import index_tail
        count = index_tail.index_pages(
            session,
            "https://cafe.naver.com/test",
            [1],
            snapshot_max_id=1000,
        )

    assert count == 1  # 998만 저장
    assert article_exists(998)
    assert not article_exists(1005)
    assert not article_exists(1003)


def test_index_pages_no_snapshot_indexes_all(tmp_path):
    """snapshot_max_id=None → 모든 article_id 저장."""
    rows_page1 = [
        {"article_id": 1005, "title": "글A", "url": "https://cafe.naver.com/a/1005", "posted_at": "2026-05-02"},
        {"article_id": 998,  "title": "글B", "url": "https://cafe.naver.com/a/998",  "posted_at": "2026-04-01"},
    ]

    session = _make_session({})

    with patch("index_tail.parse_article_list", return_value=rows_page1), \
         patch("index_tail.check_blocked", return_value=None), \
         patch("index_tail._sleep"):
        import index_tail
        count = index_tail.index_pages(
            session,
            "https://cafe.naver.com/test",
            [1],
            snapshot_max_id=None,
        )

    assert count == 2
    assert article_exists(1005)
    assert article_exists(998)


# ── _collect_after_snapshot ───────────────────────────────────────────────────

def test_collect_after_snapshot_indexes_only_new_articles(tmp_path):
    """min_id=1001 → id>=1001만 저장, id<1001 만나면 종료."""
    page1_rows = [
        {"article_id": 1003, "title": "신규1", "url": "https://cafe.naver.com/a/1003", "posted_at": "2026-05-02"},
        {"article_id": 1001, "title": "신규2", "url": "https://cafe.naver.com/a/1001", "posted_at": "2026-05-02"},
        {"article_id": 999,  "title": "기존1", "url": "https://cafe.naver.com/a/999",  "posted_at": "2026-04-01"},
    ]

    session = _make_session({})

    with patch("index_tail.parse_article_list", return_value=page1_rows), \
         patch("index_tail.check_blocked", return_value=None), \
         patch("index_tail._sleep"):
        import index_tail
        count = index_tail._collect_after_snapshot(
            session,
            "https://cafe.naver.com/test",
            min_id=1001,
        )

    assert count == 2
    assert article_exists(1003)
    assert article_exists(1001)
    assert not article_exists(999)
    # page 1에서 기존 글 만났으므로 goto는 1번만 호출
    assert session.goto.call_count == 1


def test_collect_after_snapshot_skips_already_existing(tmp_path):
    """min_id 이상이라도 이미 DB에 있으면 저장 안 함."""
    existing = Article(
        article_id=1002,
        url="https://cafe.naver.com/a/1002",
        status=Status.BODY_COLLECTED,
    )
    upsert_article(existing)

    page1_rows = [
        {"article_id": 1002, "title": "이미있음", "url": "https://cafe.naver.com/a/1002", "posted_at": "2026-05-02"},
        {"article_id": 1001, "title": "신규",     "url": "https://cafe.naver.com/a/1001", "posted_at": "2026-05-02"},
        {"article_id": 999,  "title": "기존",     "url": "https://cafe.naver.com/a/999",  "posted_at": "2026-04-01"},
    ]

    session = _make_session({})

    with patch("index_tail.parse_article_list", return_value=page1_rows), \
         patch("index_tail.check_blocked", return_value=None), \
         patch("index_tail._sleep"):
        import index_tail
        count = index_tail._collect_after_snapshot(
            session,
            "https://cafe.naver.com/test",
            min_id=1001,
        )

    assert count == 1  # 1001만 신규 저장
