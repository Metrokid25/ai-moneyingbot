"""Unit tests for the unattended RAG incremental-index wrapper + Telegram notifier.

No subprocess, no network: run_indexer_once and send_telegram are monkeypatched.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
for _p in (str(SCRIPTS_DIR),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import notify_telegram  # noqa: E402
import run_rag_incremental_notify as wrapper  # noqa: E402


@pytest.fixture(autouse=True)
def _asset_preflight_passes(monkeypatch):
    monkeypatch.setattr(
        wrapper,
        "run_asset_check_once",
        lambda **kwargs: subprocess.CompletedProcess(
            args=["check"], returncode=0, stdout='{"status":"PASS"}', stderr=""
        ),
    )


# ── parse_summary ──────────────────────────────────────────────────────────

def test_parse_summary_extracts_json_block():
    stdout = 'some log line\n{\n  "new_chunks": 3,\n  "collection": "c"\n}\n'
    assert wrapper.parse_summary(stdout) == {"new_chunks": 3, "collection": "c"}


def test_parse_summary_returns_none_on_garbage():
    assert wrapper.parse_summary("no json here") is None


def test_parse_summary_tolerates_leading_brace_noise():
    # A log line containing braces before the real summary must not corrupt it.
    stdout = 'loaded config {mode: local}\n{\n  "new_chunks": 7,\n  "collection": "c"\n}\n'
    assert wrapper.parse_summary(stdout) == {"new_chunks": 7, "collection": "c"}


def test_parse_summary_tolerates_trailing_json_noise():
    # Library teardown printing a bare {} (or a non-summary object) AFTER the
    # summary must not replace it — anchor on the summary's signature keys.
    stdout = '{"new_chunks": 4, "collection": "c"}\n{}\n{"telemetry": true}\n'
    assert wrapper.parse_summary(stdout) == {"new_chunks": 4, "collection": "c"}


# ── message building ───────────────────────────────────────────────────────

def test_success_message_reports_new_chunks():
    msg = wrapper.build_success_message(
        {"new_chunks": 5, "current_chunks": 100, "indexed_chunks": 95, "collection": "goodmorning_chunks"},
        timestamp="2026-07-05 16:30 KST",
    )
    assert "신규 5청크" in msg
    assert "goodmorning_chunks" in msg
    assert "2026-07-05 16:30 KST" in msg


def test_success_message_handles_zero_new():
    msg = wrapper.build_success_message({"new_chunks": 0}, timestamp="t")
    assert "신규 0건" in msg
    assert "최신" in msg


def test_success_message_labels_dry_run_as_detected_not_added():
    msg = wrapper.build_success_message(
        {"new_chunks": 5, "dry_run": True}, timestamp="t"
    )
    assert "신규 5청크 감지" in msg
    assert "미반영" in msg
    assert "추가" not in msg


def test_success_message_includes_collection_liveness():
    msg = wrapper.build_success_message(
        {"new_chunks": 0}, timestamp="t", last_collected="2026.07.04. 09:10"
    )
    assert "마지막 수집글 작성일: 2026.07.04. 09:10" in msg


def test_success_message_liveness_unknown_when_probe_fails():
    msg = wrapper.build_success_message({"new_chunks": 0}, timestamp="t", last_collected=None)
    assert "마지막 수집글 작성일: 확인불가" in msg


# ── collection-liveness probe ──────────────────────────────────────────────

def _make_archive_db(path, rows):
    import sqlite3

    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE articles (article_id INTEGER PRIMARY KEY, posted_at TEXT,"
        " saved_at TEXT, status TEXT)"
    )
    conn.executemany("INSERT INTO articles VALUES (?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_get_last_collected_returns_latest_body_collected(tmp_path):
    db = tmp_path / "a.db"
    # Deliberately de-correlate saved_at from article_id. The liveness signal is
    # the newest forward-collected cafe article, identified by Naver's monotonic
    # article_id, not the most recently re-saved/backfilled old article.
    _make_archive_db(
        db,
        [
            (1, "2026.07.02. 08:00", "2026-07-05T00:00:00Z", "BODY_COLLECTED"),
            (2, "2026.07.04. 09:10", "2026-07-01T00:00:00Z", "BODY_COLLECTED"),
            (3, "2026.07.05. 10:00", "2026-07-06T00:00:00Z", "INDEXED"),  # not collected yet
        ],
    )
    assert wrapper.get_last_collected(db) == "2026.07.04. 09:10"


def test_get_last_collected_query_uses_primary_key_order(tmp_path, monkeypatch):
    db = tmp_path / "plan.db"
    _make_archive_db(
        db,
        [
            (1, "old", "2026-07-05T00:00:00Z", "BODY_COLLECTED"),
            (2, "new", "2026-07-01T00:00:00Z", "BODY_COLLECTED"),
        ],
    )
    real_connect = wrapper.sqlite3.connect
    executed = []

    class TracedConnection:
        def __init__(self, inner):
            self._inner = inner

        def execute(self, sql, *args):
            executed.append(sql)
            return self._inner.execute(sql, *args)

        def close(self):
            self._inner.close()

    def traced_connect(*args, **kwargs):
        return TracedConnection(real_connect(*args, **kwargs))

    monkeypatch.setattr(wrapper.sqlite3, "connect", traced_connect)

    assert wrapper.get_last_collected(db) == "new"
    query = next(sql for sql in executed if "FROM articles" in sql)
    assert "ORDER BY article_id DESC" in query
    assert "ORDER BY saved_at" not in query


def test_get_last_collected_falls_back_to_saved_at_when_posted_at_null(tmp_path):
    db = tmp_path / "b.db"
    _make_archive_db(db, [(1, None, "2026-07-05T01:02:03Z", "BODY_COLLECTED")])
    assert wrapper.get_last_collected(db) == "2026-07-05T01:02:03Z"


def test_get_last_collected_none_on_empty_or_missing(tmp_path):
    empty = tmp_path / "empty.db"
    _make_archive_db(empty, [])
    assert wrapper.get_last_collected(empty) is None
    assert wrapper.get_last_collected(tmp_path / "does_not_exist.db") is None


def test_failure_message_truncates_long_detail():
    detail = "z" * 2000
    msg = wrapper.build_failure_message(attempts=3, detail=detail, timestamp="t")
    assert "재시도 3회 소진" in msg
    # 800-char cap on the detail body keeps the Telegram message bounded:
    # exactly 800 of the detail chars survive, not 801.
    assert ("z" * 800) in msg
    assert ("z" * 801) not in msg


# ── retry loop ─────────────────────────────────────────────────────────────

def _fake_proc(returncode, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=["x"], returncode=returncode, stdout=stdout, stderr=stderr)


def _summary_stdout(*, new_chunks=0, dry_run=False):
    return json.dumps(
        {
            "new_chunks": new_chunks,
            "current_chunks": 100,
            "indexed_chunks": 100 - new_chunks,
            "collection": "goodmorning_chunks",
            "dry_run": dry_run,
            "execute": not dry_run,
        }
    )


def test_main_success_on_first_attempt_sends_success(monkeypatch):
    sent = []
    monkeypatch.setattr(wrapper, "send_telegram", lambda text, **k: sent.append(text) or True)
    monkeypatch.setattr(wrapper, "get_last_collected", lambda p: "2026.07.05. 09:00")
    monkeypatch.setattr(
        wrapper,
        "run_indexer_once",
        lambda **k: _fake_proc(0, stdout=_summary_stdout(new_chunks=2)),
    )
    rc = wrapper.main(["--max-attempts", "3", "--backoff-seconds", "0"])
    assert rc == 0
    assert len(sent) == 1
    assert "신규 2청크" in sent[0]
    assert "마지막 수집글 작성일: 2026.07.05. 09:00" in sent[0]


def test_main_retries_then_fails_and_notifies(monkeypatch):
    calls = {"n": 0}
    sleeps = []
    sent = []

    def always_fail(**k):
        calls["n"] += 1
        return _fake_proc(1, stderr="VOYAGE_API_KEY is required")

    monkeypatch.setattr(wrapper, "run_indexer_once", always_fail)
    monkeypatch.setattr(wrapper, "send_telegram", lambda text, **k: sent.append(text) or True)
    monkeypatch.setattr(wrapper.time, "sleep", lambda s: sleeps.append(s))

    rc = wrapper.main(["--max-attempts", "3", "--backoff-seconds", "7"])
    assert rc == 1
    assert calls["n"] == 3  # retried up to the cap
    assert sleeps == [7, 7]  # backoff slept between attempts, not after the last
    assert len(sent) == 1
    assert "실패" in sent[0]
    assert "VOYAGE_API_KEY" in sent[0]


def test_main_does_not_retry_on_usage_error_rc2(monkeypatch):
    calls = {"n": 0}
    sent = []

    def usage_error(**k):
        calls["n"] += 1
        return _fake_proc(2, stderr="--dry-run and --execute are mutually exclusive")

    monkeypatch.setattr(wrapper, "run_indexer_once", usage_error)
    monkeypatch.setattr(wrapper, "send_telegram", lambda text, **k: sent.append(text) or True)
    monkeypatch.setattr(wrapper.time, "sleep", lambda *_: None)

    rc = wrapper.main(["--max-attempts", "3", "--backoff-seconds", "0"])
    assert rc == 1
    assert calls["n"] == 1  # permanent usage error: no wasted retries
    assert "재시도 1회 소진" in sent[0]


def test_notify_warns_when_delivery_fails(monkeypatch, capsys):
    monkeypatch.setattr(wrapper, "send_telegram", lambda text, **k: False)
    wrapper.notify("hello", enabled=True)
    out = capsys.readouterr().out
    assert "NOT delivered" in out


def test_main_no_telegram_flag_skips_send(monkeypatch):
    sent = []
    monkeypatch.setattr(wrapper, "send_telegram", lambda text, **k: sent.append(text) or True)
    monkeypatch.setattr(
        wrapper, "run_indexer_once", lambda **k: _fake_proc(0, stdout=_summary_stdout())
    )
    rc = wrapper.main(["--no-telegram"])
    assert rc == 0
    assert sent == []


def test_main_rejects_rc0_without_required_summary(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr(wrapper, "send_telegram", lambda text, **kwargs: sent.append(text) or True)
    monkeypatch.setattr(
        wrapper,
        "run_indexer_once",
        lambda **kwargs: _fake_proc(0, stdout='{"new_chunks": 2, "collection": "c"}'),
    )

    rc = wrapper.main(["--max-attempts", "3", "--backoff-seconds", "0"])

    assert rc == 1
    assert len(sent) == 1
    assert "invalid indexer success output" in sent[0]
    assert "invalid summary" in capsys.readouterr().out


def test_main_preflight_failure_blocks_indexer(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(
        wrapper,
        "run_asset_check_once",
        lambda **kwargs: _fake_proc(1, stdout='{"status":"FAIL","error":"count mismatch"}'),
    )
    monkeypatch.setattr(wrapper, "run_indexer_once", lambda **kwargs: called.append(kwargs))

    rc = wrapper.main(["--no-telegram"])

    assert rc == 1
    assert called == []
    assert "deployment asset preflight failed" in capsys.readouterr().out


def test_run_indexer_once_passes_baseline_paths(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _fake_proc(0, stdout="{}")

    monkeypatch.setattr(wrapper.subprocess, "run", fake_run)
    wrapper.run_indexer_once(
        python_exe="python",
        db_path=tmp_path / "archive.db",
        qdrant_path=tmp_path / "qdrant",
        manifest_path=tmp_path / "manifest.jsonl",
        seed_ids_path=tmp_path / "seed.npy",
        collection="goodmorning_chunks",
        dry_run=True,
    )

    cmd = captured["cmd"]
    assert cmd[0] == "python"
    assert "--dry-run" in cmd
    assert cmd[cmd.index("--manifest-path") + 1].endswith("manifest.jsonl")
    assert cmd[cmd.index("--seed-ids-path") + 1].endswith("seed.npy")


# ── telegram payload ───────────────────────────────────────────────────────

def test_telegram_payload_and_url():
    assert notify_telegram.build_send_url("TOK", api_base="https://api.telegram.org") == (
        "https://api.telegram.org/botTOK/sendMessage"
    )
    payload = notify_telegram.build_payload("123", "hi")
    assert payload["chat_id"] == "123"
    assert payload["text"] == "hi"


def test_send_telegram_skips_when_unconfigured(monkeypatch, capsys):
    monkeypatch.delenv(notify_telegram.ENV_TOKEN, raising=False)
    monkeypatch.delenv(notify_telegram.ENV_CHAT_ID, raising=False)
    assert notify_telegram.send_telegram("hi", token=None, chat_id=None) is False
    assert not notify_telegram.telegram_configured(token=None, chat_id=None)
