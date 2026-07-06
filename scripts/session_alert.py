"""Archive봇 세션 만료 텔레그램 알림.

인프라: RAG봇의 기존 텔레그램(scripts/notify_telegram.py + RAG_TELEGRAM_* env)을
**재사용**한다. notify_telegram.py 자체는 수정하지 않고 import만 한다(소유: RAG봇).
새 env 키를 만들지 않는다 — 토큰/채널은 RAG_TELEGRAM_BOT_TOKEN/CHAT_ID 그대로.

원칙:
- 트리거: member API 프로브(check_member_login)가 False(로그인 필요/code 0004 계열) 확정 시.
  순단(일시적 네트워크/게이트웨이 블립) 방어를 위해 1회 재프로브 후에만 알림.
- 알림 주체 구분: 메시지 첫 줄에 "[Archive] 세션 만료 감지" 프리픽스 → RAG 색인 알림과 안 섞임.
- 중복 방지: 만료 지속 중 매 주기 재발송 금지. 최초 1회 + 이후 24시간 간격 리마인더.
  재로그인으로 정상 복귀하면 상태를 리셋(다음 만료 때 즉시 재알림).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

ALERT_PREFIX = "[Archive] 세션 만료 감지"
REMINDER_INTERVAL_HOURS = 24.0


def _load_state(state_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(state_path: Path, data: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clear_alert_state(state_path: Path) -> None:
    """정상 복귀 시 호출 — 다음 만료 때 최초 알림이 즉시 나가도록 상태 제거."""
    try:
        state_path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def should_send(
    state: dict[str, Any],
    now: datetime,
    *,
    reminder_interval_hours: float = REMINDER_INTERVAL_HOURS,
) -> bool:
    """중복 방지 판정: 최초(기록 없음) 또는 마지막 발송 후 리마인더 간격 경과 시 True."""
    last = state.get("last_alert_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last))
    except (ValueError, TypeError):
        return True
    return (now - last_dt) >= timedelta(hours=reminder_interval_hours)


def build_message(detail: Optional[str], now: datetime) -> str:
    return (
        f"{ALERT_PREFIX}\n"
        "네이버 카페 수집이 중단됐습니다. 재로그인이 필요합니다.\n"
        f"사유: {detail or '-'}\n"
        f"감지: {now.isoformat(timespec='seconds')}\n"
        "조치: scripts/daily_archive.py --login (헤디드) 로 재로그인하면 자동 재개됩니다."
    )


def maybe_alert_session_expiry(
    login_checker: Callable[[], tuple[Optional[bool], Optional[str]]],
    *,
    state_path: Path,
    now: datetime,
    sender: Optional[Callable[[str], bool]] = None,
    reminder_interval_hours: float = REMINDER_INTERVAL_HOURS,
    reprobe: bool = True,
) -> dict[str, Any]:
    """만료(False) 확정 시 1회 재프로브 후 알림(중복 방지). 결과 dict 반환.

    login_checker: () -> (True|False|None, detail)  — True=정상, False=로그인필요 확정,
                   None=판별불가(프로브 실패). 테스트/무브라우저용으로 주입.
    sender: (text) -> bool  — 기본 None이면 notify_telegram.send_telegram 지연 import.
    반환: {expired, alerted, detail, sent_ok?}
    """
    logged_in, detail = login_checker()

    # 정상(True)이면 상태 리셋(복귀). 판별불가(None)면 아무 것도 안 함(순단일 수 있음).
    if logged_in is not False:
        if logged_in is True:
            clear_alert_state(state_path)
        return {"expired": False, "alerted": False, "detail": detail}

    # 순단 방어 재프로브 — 두 번째도 False여야 만료 확정.
    if reprobe:
        logged_in, detail = login_checker()
        if logged_in is not False:
            if logged_in is True:
                clear_alert_state(state_path)
            return {"expired": False, "alerted": False, "detail": detail}

    # 만료 확정 — 중복 방지 판정.
    state = _load_state(state_path)
    if not should_send(state, now, reminder_interval_hours=reminder_interval_hours):
        return {"expired": True, "alerted": False, "detail": detail}

    if sender is None:
        from notify_telegram import send_telegram as sender  # RAG봇 소유물 재사용(수정 안 함)

    text = build_message(detail, now)
    sent_ok = bool(sender(text))

    # 발송 성공 시에만 dedup 기록. 실패(토큰 미설정/네트워크)면 상태를 안 남겨
    # 다음 주기에 재시도하게 한다(전달 안 된 알림을 24시간 침묵시키지 않음).
    if sent_ok:
        state["last_alert_at"] = now.isoformat()
        state["last_detail"] = detail
        _save_state(state_path, state)
    return {"expired": True, "alerted": sent_ok, "detail": detail, "sent_ok": sent_ok}
