import sys
from datetime import datetime, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import session_alert


class _Checker:
    """호출마다 큐의 다음 (state, detail)를 반환하는 프로브 스텁."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if len(self._results) == 1:
            return self._results[0]
        return self._results.pop(0)


class _Sender:
    def __init__(self, ok=True):
        self.ok = ok
        self.messages = []

    def __call__(self, text):
        self.messages.append(text)
        return self.ok


NOW = datetime(2026, 7, 6, 9, 0, 0)


# ── should_send (중복 방지 판정) ──────────────────────────────────────────────

def test_should_send_first_time_true():
    assert session_alert.should_send({}, NOW) is True


def test_should_send_within_interval_false():
    state = {"last_alert_at": (NOW - timedelta(hours=5)).isoformat()}
    assert session_alert.should_send(state, NOW) is False


def test_should_send_after_interval_true():
    state = {"last_alert_at": (NOW - timedelta(hours=25)).isoformat()}
    assert session_alert.should_send(state, NOW) is True


def test_should_send_corrupt_timestamp_true():
    assert session_alert.should_send({"last_alert_at": "not-a-date"}, NOW) is True


# ── maybe_alert_session_expiry ────────────────────────────────────────────────

def test_confirmed_expiry_sends_with_prefix_and_persists(tmp_path):
    state_path = tmp_path / "session_alert.json"
    checker = _Checker([(False, "login_required: member_api code=0004 (로그인하지 않았습니다)")])
    sender = _Sender()

    res = session_alert.maybe_alert_session_expiry(
        checker, state_path=state_path, now=NOW, sender=sender
    )

    assert res["expired"] is True and res["alerted"] is True and res["sent_ok"] is True
    assert checker.calls == 2  # 최초 + 순단 방어 재프로브
    assert len(sender.messages) == 1
    assert sender.messages[0].splitlines()[0] == session_alert.ALERT_PREFIX
    assert "code=0004" in sender.messages[0]
    assert state_path.exists()  # last_alert_at 기록됨


def test_transient_false_then_true_does_not_send(tmp_path):
    # 첫 프로브 False였지만 재프로브에서 True → 순단으로 판단, 알림 안 함
    state_path = tmp_path / "session_alert.json"
    checker = _Checker([(False, "login_required: http_503"), (True, "ok (20 rows)")])
    sender = _Sender()

    res = session_alert.maybe_alert_session_expiry(
        checker, state_path=state_path, now=NOW, sender=sender
    )

    assert res["expired"] is False and res["alerted"] is False
    assert checker.calls == 2  # 순단 방어 재프로브가 실제로 돌았는지 잠금
    assert sender.messages == []


def test_none_on_reprobe_does_not_send(tmp_path):
    # 첫 프로브 False, 재프로브 None(판별불가) → 만료 미확정 → 침묵(설계 의도). self-heal은 다음 재시작에서.
    state_path = tmp_path / "session_alert.json"
    checker = _Checker([(False, "login_required: code=0004"), (None, "probe_failed: net")])
    sender = _Sender()

    res = session_alert.maybe_alert_session_expiry(
        checker, state_path=state_path, now=NOW, sender=sender
    )

    assert res["expired"] is False and res["alerted"] is False
    assert checker.calls == 2
    assert sender.messages == []


def test_none_probe_does_not_send(tmp_path):
    state_path = tmp_path / "session_alert.json"
    checker = _Checker([(None, "probe_failed: boom")])
    sender = _Sender()

    res = session_alert.maybe_alert_session_expiry(
        checker, state_path=state_path, now=NOW, sender=sender
    )

    assert res["expired"] is False and res["alerted"] is False
    assert sender.messages == []
    assert checker.calls == 1  # None이면 재프로브 없이 종료


def test_dedup_no_resend_within_interval(tmp_path):
    state_path = tmp_path / "session_alert.json"
    state_path.write_text(
        '{"last_alert_at": "' + (NOW - timedelta(hours=1)).isoformat() + '"}',
        encoding="utf-8",
    )
    checker = _Checker([(False, "login_required: code=0004")])
    sender = _Sender()

    res = session_alert.maybe_alert_session_expiry(
        checker, state_path=state_path, now=NOW, sender=sender
    )

    assert res["expired"] is True and res["alerted"] is False
    assert sender.messages == []  # 중복 방지로 미발송


def test_reminder_resends_after_interval(tmp_path):
    state_path = tmp_path / "session_alert.json"
    state_path.write_text(
        '{"last_alert_at": "' + (NOW - timedelta(hours=25)).isoformat() + '"}',
        encoding="utf-8",
    )
    checker = _Checker([(False, "login_required: code=0004")])
    sender = _Sender()

    res = session_alert.maybe_alert_session_expiry(
        checker, state_path=state_path, now=NOW, sender=sender
    )

    assert res["alerted"] is True
    assert len(sender.messages) == 1


def test_recovery_true_clears_state(tmp_path):
    state_path = tmp_path / "session_alert.json"
    state_path.write_text('{"last_alert_at": "2026-07-05T09:00:00"}', encoding="utf-8")
    checker = _Checker([(True, "ok (20 rows)")])
    sender = _Sender()

    res = session_alert.maybe_alert_session_expiry(
        checker, state_path=state_path, now=NOW, sender=sender
    )

    assert res["expired"] is False and res["alerted"] is False
    assert not state_path.exists()  # 복귀 시 상태 리셋
    assert sender.messages == []


def test_send_failure_records_attempt_and_floors_rapid_retry(tmp_path):
    # 발송 실패(잘못된 토큰 등)여도 '시도'는 기록해 재시작마다 무한 스팸을 막고,
    # 하한 간격이 지나면 재시도한다.
    state_path = tmp_path / "session_alert.json"
    sender = _Sender(ok=False)

    r1 = session_alert.maybe_alert_session_expiry(
        _Checker([(False, "login_required: code=0004")]),
        state_path=state_path, now=NOW, sender=sender,
    )
    assert r1["sent_ok"] is False and r1["alerted"] is False
    assert len(sender.messages) == 1        # 시도는 함
    assert state_path.exists()              # last_attempt_at 기록(성공 아님)

    # 하한(30분) 안의 재시도는 억제 → 스팸 방지
    r2 = session_alert.maybe_alert_session_expiry(
        _Checker([(False, "login_required: code=0004")]),
        state_path=state_path, now=NOW + timedelta(minutes=10), sender=sender,
    )
    assert r2["alerted"] is False
    assert len(sender.messages) == 1        # 재발송 시도 없음

    # 하한 경과 후에는 재시도
    r3 = session_alert.maybe_alert_session_expiry(
        _Checker([(False, "login_required: code=0004")]),
        state_path=state_path, now=NOW + timedelta(minutes=31), sender=sender,
    )
    assert len(sender.messages) == 2        # 재시도 발생


def test_tz_mixed_timestamp_does_not_crash(tmp_path):
    # 상태에 tz-aware 타임스탬프가 있고 now는 naive여도 뺄셈 TypeError 없이 발송 허용.
    state_path = tmp_path / "session_alert.json"
    state_path.write_text('{"last_attempt_at": "2026-07-05T09:00:00+09:00"}', encoding="utf-8")
    sender = _Sender()

    res = session_alert.maybe_alert_session_expiry(
        _Checker([(False, "login_required: code=0004")]),
        state_path=state_path, now=NOW, sender=sender,
    )

    assert res["alerted"] is True  # 크래시 없이 발송(보수적 허용)
    assert len(sender.messages) == 1


def test_clear_alert_state_missing_is_noop(tmp_path):
    session_alert.clear_alert_state(tmp_path / "nope.json")  # 예외 없이 통과


def test_build_message_first_line_is_archive_prefix():
    msg = session_alert.build_message("login_required: code=0004", NOW)
    assert msg.splitlines()[0] == "[Archive] 세션 만료 감지"
    assert "재로그인" in msg
