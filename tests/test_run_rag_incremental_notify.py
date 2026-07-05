"""Unit tests for the unattended RAG incremental-index wrapper + Telegram notifier.

No subprocess, no network: run_indexer_once and send_telegram are monkeypatched.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
for _p in (str(SCRIPTS_DIR),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import notify_telegram  # noqa: E402
import run_rag_incremental_notify as wrapper  # noqa: E402


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


def test_failure_message_truncates_long_detail():
    detail = "x" * 2000
    msg = wrapper.build_failure_message(attempts=3, detail=detail, timestamp="t")
    assert "재시도 3회 소진" in msg
    # 800-char cap on the detail body keeps the Telegram message bounded.
    assert msg.count("x") == 800


# ── retry loop ─────────────────────────────────────────────────────────────

def _fake_proc(returncode, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=["x"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_main_success_on_first_attempt_sends_success(monkeypatch):
    sent = []
    monkeypatch.setattr(wrapper, "send_telegram", lambda text, **k: sent.append(text) or True)
    monkeypatch.setattr(
        wrapper,
        "run_indexer_once",
        lambda **k: _fake_proc(0, stdout='{"new_chunks": 2, "collection": "c"}'),
    )
    rc = wrapper.main(["--max-attempts", "3", "--backoff-seconds", "0"])
    assert rc == 0
    assert len(sent) == 1
    assert "신규 2청크" in sent[0]


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
    monkeypatch.setattr(wrapper, "run_indexer_once", lambda **k: _fake_proc(0, stdout='{"new_chunks": 0}'))
    rc = wrapper.main(["--no-telegram"])
    assert rc == 0
    assert sent == []


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
