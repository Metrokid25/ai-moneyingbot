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
    revision_hash,
)


MASTER = {
    "version": 3,
    "by_code": {
        "005930": "삼성전자",
        "000660": "SK하이닉스",
        "042660": "한화오션",
        "100001": "와이엠",
        "100002": "와이엠씨",
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
    assert source.conn.execute("PRAGMA query_only").fetchone()[0] == 1
    with pytest.raises(sqlite3.OperationalError):
        source.conn.execute("CREATE TABLE forbidden_write(id INTEGER)")


def test_state_store_rejects_archive_path_before_opening_it(tmp_path):
    archive_path = make_archive(tmp_path)
    with pytest.raises(ValueError, match="must not be the Archive DB"):
        StateStore(archive_path, forbidden_path=archive_path)
    con = sqlite3.connect(archive_path)
    assert con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='reader_meta'"
    ).fetchone()[0] == 0
    con.close()


def test_state_store_detects_archive_without_explicit_forbidden_path(tmp_path):
    archive_path = make_archive(tmp_path)
    with pytest.raises(ValueError, match="must not be an Archive DB"):
        StateStore(archive_path)
    con = sqlite3.connect(archive_path)
    assert con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='reader_meta'"
    ).fetchone()[0] == 0
    con.close()


def test_exact_stock_title_is_pick_even_when_body_is_empty(tmp_path):
    parser = RuleParser(make_master(tmp_path))
    signal = parser.parse(article=article_row(tmp_path, "", title="삼성전자..."), mode="shadow")
    assert signal.signal_type == "ADD_WATCH"
    assert [stock["code"] for stock in signal.stocks] == ["005930"]
    assert signal.confidence >= 0.99


def test_feature_title_extracts_structured_stock_lines(tmp_path):
    parser = RuleParser(make_master(tmp_path))
    row = article_row(tmp_path, "시장 설명\n- 삼성전자\n- SK하이닉스", title="오늘의 특징주")
    signal = parser.parse(article=row, mode="shadow")
    assert signal.signal_type == "ADD_WATCH"
    assert {stock["code"] for stock in signal.stocks} == {"005930", "000660"}
    assert signal.confidence >= 0.98


def test_feature_title_keeps_per_stock_negative_override(tmp_path):
    parser = RuleParser(make_master(tmp_path))
    row = article_row(
        tmp_path,
        "- 삼성전자\n삼성전자는 추격하지 마세요.\n- SK하이닉스",
        title="특징주",
    )
    signals = parser.parse_all(article=row, mode="shadow")
    by_type = {signal.signal_type: [stock["code"] for stock in signal.stocks] for signal in signals}
    assert by_type["DO_NOT_BUY"] == ["005930"]
    assert by_type["ADD_WATCH"] == ["000660"]


def test_feature_name_code_header_inherits_next_line_negative(tmp_path):
    parser = RuleParser(make_master(tmp_path))
    row = article_row(
        tmp_path, "- 삼성전자(005930)\n추격하지 마세요", title="특징주"
    )
    signal = parser.parse(article=row, mode="shadow")
    assert signal.signal_type == "DO_NOT_BUY"
    assert [stock["code"] for stock in signal.stocks] == ["005930"]


def test_macro_title_only_promotes_structured_tail_stocks(tmp_path):
    parser = RuleParser(make_master(tmp_path))
    row = article_row(
        tmp_path,
        "삼성전자 실적 발표가 있었습니다.\n거시 설명1\n거시 설명2\n거시 설명3\n"
        "마지막 관심 종목입니다.\n- SK하이닉스",
        title="다음 주는........",
    )
    signal = parser.parse(article=row, mode="shadow")
    assert signal.signal_type == "ADD_WATCH"
    assert [stock["code"] for stock in signal.stocks] == ["000660"]
    assert signal.confidence == 0.96


def test_title_change_changes_revision_hash_and_legacy_time_becomes_iso(tmp_path):
    parser = RuleParser(make_master(tmp_path))
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = parser.parse(article=article_row(first_dir, "", title="삼성전자"), mode="shadow")
    second = parser.parse(article=article_row(second_dir, "", title="SK하이닉스"), mode="shadow")
    assert first.article_revision_hash != second.article_revision_hash
    assert first.posted_at == "2026-08-05T10:00:00+09:00"


def test_longest_stock_name_wins_without_substring_duplicate(tmp_path):
    stocks = make_master(tmp_path).candidates("오늘은 와이엠씨를 관심 있게 봅니다")
    assert [(stock.code, stock.name) for stock in stocks] == [("100002", "와이엠씨")]


def test_revision_hash_preserves_signal_relevant_line_boundaries():
    assert revision_hash("특징주", "삼성전자 SK하이닉스") != revision_hash(
        "특징주", "삼성전자\nSK하이닉스"
    )


def test_third_party_selling_is_not_exit_or_feature_add(tmp_path):
    parser = RuleParser(make_master(tmp_path))
    row = article_row(
        tmp_path, "- 삼성전자\n외인들이 삼성전자를 계속 매도중입니다", title="특징주"
    )
    signal = parser.parse(article=row, mode="shadow")
    assert signal.signal_type == "NO_SIGNAL"
    assert signal.stocks == []


@pytest.mark.parametrize(
    "text",
    [
        "외인들의 삼성전자 손절물량이 출회되고 있습니다",
        "삼성전자는 비중축소에 해당되지 않는다",
        "삼성전자 수익실현이 나온다면 시장을 다시 봅니다",
    ],
)
def test_exit_words_without_mentor_exit_instruction_are_blocked(tmp_path, text):
    parser = RuleParser(make_master(tmp_path))
    signal = parser.parse(article=article_row(tmp_path, text, title="특징주"), mode="shadow")
    assert signal.signal_type == "NO_SIGNAL"


def test_later_reentry_action_wins_over_earlier_exit_background(tmp_path):
    parser = RuleParser(make_master(tmp_path))
    signal = parser.parse(
        article=article_row(
            tmp_path,
            "다른 종목은 수익실현후 삼성전자로 갈아타는 대응이 필요합니다",
            title="오늘은........",
        ),
        mode="shadow",
    )
    assert signal.signal_type == "ADD_WATCH"
    assert [stock["code"] for stock in signal.stocks] == ["005930"]


@pytest.mark.parametrize(
    "text",
    [
        "삼성전자는 좋아 보이지 않습니다",
        "삼성전자는 홀딩하지 마세요",
        "삼성전자는 매수 사인이 아닙니다",
        "삼성전자는 공매도 비중을 체크합니다",
    ],
)
def test_negated_positive_and_market_metric_are_not_add_watch(tmp_path, text):
    signal = RuleParser(make_master(tmp_path)).parse(
        article=article_row(tmp_path, text), mode="shadow"
    )
    assert signal.signal_type != "ADD_WATCH"


@pytest.mark.parametrize(
    "text",
    [
        "외인들이 삼성전자를 일부 매도했습니다",
        "기관은 삼성전자를 전량 매도했습니다",
    ],
)
def test_third_party_explicit_sales_are_not_exit_signals(tmp_path, text):
    signal = RuleParser(make_master(tmp_path)).parse(
        article=article_row(tmp_path, text), mode="shadow"
    )
    assert signal.signal_type == "NO_SIGNAL"


@pytest.mark.parametrize(
    "text",
    [
        "삼성전자는 매수 후보가 아닙니다",
        "삼성전자는 매수 가능하지 않습니다",
        "삼성전자는 재진입하지 마세요",
        "삼성전자로 갈아타지 마세요",
    ],
)
def test_all_positive_phrases_honor_suffix_negation(tmp_path, text):
    signal = RuleParser(make_master(tmp_path)).parse(
        article=article_row(tmp_path, text), mode="shadow"
    )
    assert signal.signal_type != "ADD_WATCH"


def test_same_sentence_actions_are_scoped_to_each_stock_clause(tmp_path):
    signals = RuleParser(make_master(tmp_path)).parse_all(
        article=article_row(
            tmp_path, "삼성전자는 관심, SK하이닉스는 추격하지 마세요"
        ),
        mode="shadow",
    )
    by_type = {item.signal_type: [s["code"] for s in item.stocks] for item in signals}
    assert by_type == {"DO_NOT_BUY": ["000660"], "ADD_WATCH": ["005930"]}


def test_malgo_transition_keeps_each_stock_action_separate(tmp_path):
    signals = RuleParser(make_master(tmp_path)).parse_all(
        article=article_row(
            tmp_path, "삼성전자는 추격하지 말고 SK하이닉스는 관심입니다"
        ),
        mode="shadow",
    )
    by_type = {item.signal_type: [s["code"] for s in item.stocks] for item in signals}
    assert by_type == {"DO_NOT_BUY": ["005930"], "ADD_WATCH": ["000660"]}


def test_feature_list_malgo_does_not_restore_excluded_stock(tmp_path):
    signals = RuleParser(make_master(tmp_path)).parse_all(
        article=article_row(
            tmp_path, "- 삼성전자 말고 SK하이닉스를 관심", title="특징주"
        ),
        mode="shadow",
    )
    by_type = {item.signal_type: [s["code"] for s in item.stocks] for item in signals}
    assert by_type == {"DO_NOT_BUY": ["005930"], "ADD_WATCH": ["000660"]}


@pytest.mark.parametrize("connector", ["대신", "대신에"])
def test_feature_list_daesin_does_not_restore_replaced_stock(tmp_path, connector):
    signals = RuleParser(make_master(tmp_path)).parse_all(
        article=article_row(
            tmp_path, f"- 삼성전자 {connector} SK하이닉스를 관심", title="특징주"
        ),
        mode="shadow",
    )
    by_type = {item.signal_type: [s["code"] for s in item.stocks] for item in signals}
    assert by_type == {"DO_NOT_BUY": ["005930"], "ADD_WATCH": ["000660"]}


def test_later_positive_overrides_earlier_negated_positive(tmp_path):
    signal = RuleParser(make_master(tmp_path)).parse(
        article=article_row(
            tmp_path, "삼성전자는 매수 후보가 아니지만 지금은 관심입니다"
        ),
        mode="shadow",
    )
    assert signal.signal_type == "ADD_WATCH"


@pytest.mark.parametrize(
    "text",
    [
        "삼성전자는 재진입은 안 합니다",
        "삼성전자는 관심 안 둡니다",
        "삼성전자는 매수 후보로 보기는 어렵습니다",
    ],
)
def test_conversational_positive_negations_are_not_picks(tmp_path, text):
    signal = RuleParser(make_master(tmp_path)).parse(
        article=article_row(tmp_path, text), mode="shadow"
    )
    assert signal.signal_type != "ADD_WATCH"


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


def test_first_run_does_not_lose_edit_between_watermark_and_id_baseline(tmp_path, monkeypatch):
    archive_path = make_archive(tmp_path, [
        (10, "기존글", "u", "굿머닝", "2026-08-01", "시황", "시황",
         "BODY_COLLECTED", "2026-08-01T00:00:00+09:00", "2026-08-01T00:00:00+09:00")
    ])

    class MutatingArchive(ArchiveSource):
        def max_article_id(self, author):
            baseline = super().max_article_id(author)
            con = sqlite3.connect(archive_path)
            con.execute(
                "UPDATE articles SET title='삼성전자', clean_text='', raw_html='', updated_at=? "
                "WHERE article_id=10",
                ("2026-08-07T10:00:01+09:00",),
            )
            con.commit()
            con.close()
            return baseline

    monkeypatch.setattr(reader_module, "now_iso", lambda: "2026-08-07T10:00:00+09:00")
    reader = MentorSignalReader(
        archive=MutatingArchive(archive_path), state=StateStore(tmp_path / "state.db"),
        parser=RuleParser(make_master(tmp_path)), author_id="굿머닝", mode="shadow",
        confidence_threshold=0.95,
    )
    assert reader.run_once()["events"] == 0
    second = reader.run_once()
    assert second["articles"] == 1
    assert second["events"] == 1


def test_bootstrap_existing_is_shadow_only(tmp_path):
    reader = MentorSignalReader(
        archive=ArchiveSource(make_archive(tmp_path)), state=StateStore(tmp_path / "state.db"),
        parser=RuleParser(make_master(tmp_path)), author_id="굿머닝", mode="paper",
        confidence_threshold=0.95, trading_base_url="http://127.0.0.1:8000", web_key="key",
    )
    with pytest.raises(ValueError, match="only in shadow mode"):
        reader.run_once(bootstrap_existing=True)


def test_reader_processes_stock_title_with_truly_empty_body(tmp_path):
    archive = make_archive(tmp_path, [
        (10, "삼성전자", "u", "굿머닝", "2026-08-05 10:00:00", "", "",
         "BODY_COLLECTED", "2026-08-05T10:01:00+09:00", "2026-08-05T10:01:00+09:00")
    ])
    state = StateStore(tmp_path / "state.db")
    reader = MentorSignalReader(
        archive=ArchiveSource(archive), state=state, parser=RuleParser(make_master(tmp_path)),
        author_id="굿머닝", mode="shadow", confidence_threshold=0.95,
    )
    result = reader.run_once(bootstrap_existing=True)
    assert result["articles"] == 1
    assert result["events"] == 1
    row = state.conn.execute(
        "SELECT stock_code,signal_type,delivery_status FROM mentor_signal_events"
    ).fetchone()
    assert tuple(row) == ("005930", "ADD_WATCH", "shadow")


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
        return (
            len(attempts) > 1,
            "ok" if len(attempts) > 1 else "temporary failure",
            len(attempts) == 1,
        )

    monkeypatch.setattr(reader_module, "deliver", fake_deliver)
    state = StateStore(tmp_path / "state.db")
    reader = MentorSignalReader(
        archive=ArchiveSource(archive), state=state, parser=RuleParser(make_master(tmp_path)),
        author_id="굿머닝", mode="paper", confidence_threshold=0.95,
        trading_base_url="http://trading", web_key="key",
    )
    state.initialize(last_article_id=0, last_scan_at="1970-01-01T00:00:00+00:00")
    reader.run_once()
    assert state.conn.execute(
        "SELECT delivery_status FROM mentor_signal_events"
    ).fetchone()[0] == "delivery_failed"
    state.conn.execute("UPDATE mentor_signal_events SET next_retry_at=NULL")
    state.conn.commit()
    retried = reader.run_once()
    assert state.conn.execute(
        "SELECT delivery_status FROM mentor_signal_events"
    ).fetchone()[0] == "delivered"
    assert attempts == ["000660", "000660"]
    assert retried["retried"] == 1
    assert retried["retry_delivered"] == 1
    assert retried["delivered"] == 1


def test_permanent_delivery_rejection_is_not_retried(tmp_path, monkeypatch):
    archive = make_archive(tmp_path, [
        (10, "신규글", "u", "굿머닝", "2026-08-05", "SK하이닉스를 관심 있게 봅니다",
         "SK하이닉스를 관심 있게 봅니다", "BODY_COLLECTED", "2026-08-05", "2026-08-05")
    ])
    monkeypatch.setattr(
        reader_module, "deliver", lambda *args, **kwargs: (False, "HTTP 422", False)
    )
    state = StateStore(tmp_path / "state.db")
    reader = MentorSignalReader(
        archive=ArchiveSource(archive), state=state, parser=RuleParser(make_master(tmp_path)),
        author_id="굿머닝", mode="paper", confidence_threshold=0.95,
        trading_base_url="http://trading", web_key="key",
    )
    state.initialize(last_article_id=0, last_scan_at="1970-01-01T00:00:00+00:00")
    reader.run_once()
    assert state.conn.execute(
        "SELECT delivery_status FROM mentor_signal_events"
    ).fetchone()[0] == "delivery_rejected"
    assert state.pending() == []


def test_retry_backlog_query_is_bounded(tmp_path):
    state = StateStore(tmp_path / "state.db")
    payload = {
        "article_revision_hash": "a" * 64, "signal_type": "ADD_WATCH",
        "confidence": 0.97, "evidence": "e", "posted_at": None,
        "detected_at": "2026-08-07T00:00:00+09:00", "stocks": [],
    }
    for number in range(25):
        event = {**payload, "article_id": str(number)}
        state.insert_event(event, {"name": "삼성전자", "code": "005930"})
    assert len(state.pending(limit=10)) == 10
