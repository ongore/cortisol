"""Discord webhook posting (instant community alerts)."""

from __future__ import annotations

from typing import Any

import httpx

import cortisol_config as cfg


def send_discord_webhook(text: str) -> dict[str, Any]:
    url = cfg.DISCORD_ALERT_WEBHOOK_URL
    if not url:
        return {"skipped": True, "reason": "no_webhook"}
    clipped = text[:1900]
    with httpx.Client(timeout=22.0) as client:
        r = client.post(url, json={"content": clipped})
        if r.status_code in (200, 204):
            return {"skipped": False, "ok": True}
        return {"skipped": False, "ok": False, "detail": r.text[:300]}

