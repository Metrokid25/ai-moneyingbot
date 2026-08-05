from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import src.mentor_signal_reader as reader_module
from src.mentor_signal_reader import (
    ArchiveSource,
    MentorSignalReader,
    RuleParser,
    StateStore,
    StockMasterSnapshot,
)


MASTER = {
    "version": 3,
    "by_code": {
        "005930": "삼성전자",
        "000660": "SK하이닉스",
        "042660": "한화오션",
    },
}


def make_master(tmp_path: Path) -> StockMasterSnapshot:
    path = tmp_path / "stock_master.json"
    path.write_text(json.dumps(MASTER, ensure_ascii=False), encoding="utf-8")
    aliases = tmp_path / "aliases.json"
    aliases.write_text(json.dumps({"하닉": "000660"}, ensure_ascii=False), encoding="utf-8")
    return StockMasterSnapshot(path, aliases)


def make_archive(tmp_path: Path, rows: list[tuple] | None = None) -> Path:
    path = tmp_path / "archive.db"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE articles(article_id INTEGER PRIMARY KEY,title TEXT,url TEXT,author TEXT,"
        "posted_at TEXT,raw_html TEXT,clean_text TEXT,status TEXT,saved_at TEXT,updated_at TEXT)"
    )
    con.executemany(
        "INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?)",
        rows or [],
    )
    con.commit()
    con.close()
    return path


def article_row(tmp_path: Path, text: str, title: str = "장중 코멘트"):
    path = make_archive(tmp_path, [
        (1, title, "https://example/1", "굿머닝", "2026-08-05T10:00:00+09:00",
         text, text, "BODY_COLLECTED", "2026-08-05T10:01:00+09:00",
         "2026-08-05T10:01:00+09:00")
    ])
    source = ArchiveSource(path)
    return source.conn.execute("SELECT * FROM articles WHERE article_id=1").fetchone()


@pytest.mark.parametrize(
    ("text", "expected_type", "expected_codes"),
    [
        ("오늘은 한화오션을 관심 있게 봅니다.", "ADD_WATCH", ["042660"]),
        ("삼성전자는 지금 추격하지 마세요.", "DO_NOT_BUY", ["005930"]),
        ("삼성전자는 매수하지 마세요.", "DO_NOT_BUY", ["005930"]),
        ("어제 말씀드린 한화오션은 이 정도에서 정리합니다.", "EXIT_SIGNAL", ["042660"]),
        ("삼성전자보다 SK하이닉스가 더 좋아 보입니다.", "ADD_WATCH", ["000660"]),
        ("지난달 삼성전자를 말씀드렸을 때 많이 올랐습니다.", "NO_SIGNAL", []),
        ("삼성전자 실적 발표가 있었습니다.", "NO_SIGNAL", []),
        ("오늘은 원전 쪽을 봐야 합니다.", "SECTOR_WATCH", []),
        ("삼성전자 실적 발표. 오늘은 SK하이닉스를 관심 있게 봅니다.",
         "ADD_WATCH", ["000660"]),
        ("오늘은 하닉을 관심 있게 봅니다.", "ADD_WATCH", ["000660"]),
        ("오늘은 존재하지않는회사를 관심 있게 봅니다.", "NO_SIGNAL", []),
        ("삼성전자(000660)를 관심 있게 봅니다.", "REVIEW_REQUIRED", ["005930", "000660"]),
        ("", "NO_SIGNAL", []),
        ("<p>오늘은 <b>한화오션</b>을 관심 있게 봅니다.</p>", "ADD_WATCH", ["042660"]),
    ],
)
def test_rule_parser_cases(tmp_path, text, expected_type, expected_codes):
    parser = RuleParser(make_master(tmp_path))
    signal = parser.parse(article=article_row(tmp_path, text), mode="shadow")
    assert signal.signal_type == expected_type
    assert [s["code"] for s in signal.stocks] == expected_codes


def test_archive_connection_is_read_only(tmp_path):
    source = ArchiveSource(make_archive(tmp_path))
    with pytest.raises(sqlite3.OperationalError):
        source.conn.execute("CREATE TABLE forbidden_write(id INTEGER)")


def test_first_run_baselines_existing_articles(tmp_path):
    archive = make_archive(tmp_path, [
        (10, "기존글", "u", "굿머닝", "2026-08-01", "한화오션 관심", "한화오션 관심",
         "BODY_COLLECTED", "2026-08-01", "2026-08-01")
    ])
    reader = MentorSignalReader(
        archive=ArchiveSource(archive), state=StateStore(tmp_path / "state.db"),
        parser=RuleParser(make_master(tmp_path)), author_id="굿머닝", mode="shadow",
        confidence_threshold=0.95,
    )
    assert reader.run_once()["events"] == 0


def test_duplicate_is_idempotent_and_revision_is_reprocessed(tmp_path):
    archive = make_archive(tmp_path, [
        (10, "신규글", "u", "굿머닝", "2026-08-05", "한화오션 관심 있게 봅니다",
         "한화오션 관심 있게 봅니다", "BODY_COLLECTED", "2026-08-05", "2026-08-05")
    ])
    state = StateStore(tmp_path / "state.db")
    reader = MentorSignalReader(
        archive=ArchiveSource(archive), state=state, parser=RuleParser(make_master(tmp_path)),
        author_id="굿머닝", mode="shadow", confidence_threshold=0.95,
    )
    first = reader.run_once(bootstrap_existing=True)
    second = reader.run_once()
    assert first["events"] == 1
    assert second["events"] == 0

    con = sqlite3.connect(archive)
    con.execute(
        "UPDATE articles SET clean_text=?,raw_html=?,updated_at=? WHERE article_id=10",
        ("한화오션 추격하지 마세요", "한화오션 추격하지 마세요", "2099-01-01T00:00:00+09:00"),
    )
    con.commit()
    con.close()
    edited = reader.run_once()
    assert edited["events"] == 1
    types = [r[0] for r in state.conn.execute("SELECT signal_type FROM mentor_signal_events ORDER BY id")]
    assert types == ["ADD_WATCH", "DO_NOT_BUY"]


def test_live_mode_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="disabled by policy"):
        MentorSignalReader(
            archive=ArchiveSource(make_archive(tmp_path)), state=StateStore(tmp_path / "state.db"),
            parser=RuleParser(make_master(tmp_path)), author_id="굿머닝", mode="live",
            confidence_threshold=0.95,
        )


def test_failed_trading_delivery_retries_on_next_cycle(tmp_path, monkeypatch):
    archive = make_archive(tmp_path, [
        (10, "신규글", "u", "굿머닝", "2026-08-05", "SK하이닉스를 관심 있게 봅니다",
         "SK하이닉스를 관심 있게 봅니다", "BODY_COLLECTED", "2026-08-05", "2026-08-05")
    ])
    attempts = []

    def fake_deliver(payload, base_url, web_key, timeout=15.0):
        attempts.append(payload["stock_code"])
        return (len(attempts) > 1, "ok" if len(attempts) > 1 else "temporary failure")

    monkeypatch.setattr(reader_module, "deliver", fake_deliver)
    state = StateStore(tmp_path / "state.db")
    reader = MentorSignalReader(
        archive=ArchiveSource(archive), state=state, parser=RuleParser(make_master(tmp_path)),
        author_id="굿머닝", mode="paper", confidence_threshold=0.95,
        trading_base_url="http://trading", web_key="key",
    )
    reader.run_once(bootstrap_existing=True)
    assert state.conn.execute(
        "SELECT delivery_status FROM mentor_signal_events"
    ).fetchone()[0] == "delivery_failed"
    reader.run_once()
    assert state.conn.execute(
        "SELECT delivery_status FROM mentor_signal_events"
    ).fetchone()[0] == "delivered"
    assert attempts == ["000660", "000660"]
