"""Telegram Bot API sendMessage (polling worker later / manual test now)."""

from __future__ import annotations

from typing import Any

import httpx

import cortisol_config as cfg


def send_telegram_text(text: str) -> dict[str, Any]:
    tok = cfg.TELEGRAM_BOT_TOKEN
    if not tok:
        return {"skipped": True, "reason": "no_token"}
    if not cfg.TELEGRAM_ALERT_CHAT_IDS:
        return {"skipped": True, "reason": "no_chat_ids"}

    outcomes: dict[str, Any] = {}
    ok_any = False
    with httpx.Client(timeout=22.0) as client:
        for chat_id in cfg.TELEGRAM_ALERT_CHAT_IDS:
            resp = client.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": False,
                },
            )
            chat_key = str(chat_id)
            if resp.status_code == 200:
                ok_any = True
                outcomes[chat_key] = "ok"
            else:
                outcomes[chat_key] = f"{resp.status_code}:{resp.text[:300]}"
    return {"skipped": False, "ok": ok_any, "per_chat": outcomes}

