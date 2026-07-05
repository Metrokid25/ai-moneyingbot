"""Telegram notifier for the RAG bot (separate bot/channel from trading-bot).

Ownership boundary: this uses the RAG bot's OWN Telegram bot token/channel,
configured via RAG_TELEGRAM_BOT_TOKEN / RAG_TELEGRAM_CHAT_ID. It never reuses
trading-bot's Telegram infrastructure (see docs/OWNERSHIP.md).

Dependency-free: uses urllib from the stdlib (no `requests`).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

try:  # optional: load .env when run standalone
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001 - dotenv is optional at runtime
    pass

ENV_TOKEN = "RAG_TELEGRAM_BOT_TOKEN"
ENV_CHAT_ID = "RAG_TELEGRAM_CHAT_ID"
API_BASE = "https://api.telegram.org"


def build_send_url(token: str, api_base: str = API_BASE) -> str:
    return f"{api_base}/bot{token}/sendMessage"


def build_payload(chat_id: str, text: str) -> dict[str, str]:
    # disable_web_page_preview keeps status pings clean; no parse_mode so the
    # message is sent as plain text (no markdown escaping pitfalls).
    return {
        "chat_id": str(chat_id),
        "text": text,
        "disable_web_page_preview": "true",
    }


def telegram_configured(token: str | None = None, chat_id: str | None = None) -> bool:
    token = token if token is not None else os.environ.get(ENV_TOKEN)
    chat_id = chat_id if chat_id is not None else os.environ.get(ENV_CHAT_ID)
    return bool(token and chat_id)


def send_telegram(
    text: str,
    *,
    token: str | None = None,
    chat_id: str | None = None,
    timeout: float = 15.0,
    api_base: str = API_BASE,
) -> bool:
    """Send a plain-text Telegram message. Returns True on success.

    Never raises for the common failure modes (missing config, network/API
    error): a scheduled run must not crash because a notification failed. The
    failure is printed to stderr and reported via the return value.
    """
    token = token if token is not None else os.environ.get(ENV_TOKEN)
    chat_id = chat_id if chat_id is not None else os.environ.get(ENV_CHAT_ID)
    if not token or not chat_id:
        print(
            f"[notify_telegram] WARN: {ENV_TOKEN}/{ENV_CHAT_ID} not set; "
            "skipping Telegram notification.",
        )
        return False

    data = urllib.parse.urlencode(build_payload(chat_id, text)).encode("utf-8")
    req = urllib.request.Request(
        build_send_url(token, api_base),
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(body)
        if not payload.get("ok", False):
            print(f"[notify_telegram] ERROR: Telegram API returned not-ok: {body}")
            return False
        return True
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        print(f"[notify_telegram] ERROR: HTTP {exc.code}: {detail}")
        return False
    except Exception as exc:  # noqa: BLE001 - never crash the caller
        print(f"[notify_telegram] ERROR: {exc}")
        return False
