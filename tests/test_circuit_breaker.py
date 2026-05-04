"""tests/test_circuit_breaker.py — _CircuitBreaker unit tests."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from batch_recollect import (
    CIRCUIT_BREAKER_ENABLED,
    CIRCUIT_BREAKER_REASONS,
    CIRCUIT_BREAKER_THRESHOLD,
    _CircuitBreaker,
)
from collector import BlockReason
from models import Status


def _make_cb() -> _CircuitBreaker:
    return _CircuitBreaker(
        enabled=CIRCUIT_BREAKER_ENABLED,
        threshold=CIRCUIT_BREAKER_THRESHOLD,
        reasons=CIRCUIT_BREAKER_REASONS,
    )


def test_circuit_breaker_trips_on_3_consecutive_same_signal():
    """같은 block 사유 3연속 → sys.exit(2)."""
    cb = _make_cb()
    cb.record(Status.INDEXED, BlockReason.CAPTCHA)
    cb.record(Status.INDEXED, BlockReason.CAPTCHA)
    with pytest.raises(SystemExit) as exc_info:
        cb.record(Status.INDEXED, BlockReason.CAPTCHA)
    assert exc_info.value.code == 2


def test_circuit_breaker_resets_on_body_collected():
    """CAPTCHA × 2 → BODY_COLLECTED(reset) → CAPTCHA × 2: 발동 안 함."""
    cb = _make_cb()
    cb.record(Status.INDEXED, BlockReason.CAPTCHA)
    cb.record(Status.INDEXED, BlockReason.CAPTCHA)
    cb.record(Status.BODY_COLLECTED, None)
    cb.record(Status.INDEXED, BlockReason.CAPTCHA)
    cb.record(Status.INDEXED, BlockReason.CAPTCHA)
    # 5번째 호출 — reset 후 2연속이므로 발동 안 함


def test_circuit_breaker_no_trip_on_mixed_signals():
    """서로 다른 block 사유 섞임 → 카운터 reset되어 발동 안 함."""
    cb = _make_cb()
    cb.record(Status.INDEXED, BlockReason.CAPTCHA)
    cb.record(Status.INDEXED, BlockReason.LOGIN_REQUIRED)  # 다른 사유 → count=1로 reset
    cb.record(Status.INDEXED, BlockReason.CAPTCHA)          # 다시 다른 사유 → count=1
    # 3건이지만 연속 동일 사유 없음 → 발동 안 함
