"""After enriched feed computes pipeline, optionally fan-out Telegram + Discord."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import cortisol_config as cfg
from db.connection import database_url_configured
from db.signal_dispatches_repo import log_dispatch, recent_dispatch_count
from integrations.compose_alert import format_signal_message
from integrations.discord_client import send_discord_webhook
from integrations.telegram_client import send_telegram_text

_LOG = logging.getLogger("cortisol.alerts")

_mem_seen: dict[str, float] = {}
_mem_lock = threading.Lock()


def _recent_mem(chain: str, token: str, _window_s: int) -> bool:
    key = f"{chain}:{token}"
    now = time.time()
    with _mem_lock:
        expiry = _mem_seen.get(key, 0)
        return expiry > now


def _mark_mem(chain: str, token: str, window_s: int) -> None:
    key = f"{chain}:{token}"
    with _mem_lock:
        _mem_seen[key] = time.time() + window_s


def _cooldown_active(chain_id: str, token_address: str) -> bool:
    if database_url_configured():
        try:
            n = recent_dispatch_count(
                chain_id,
                token_address,
                max_age_seconds=int(cfg.ALERT_COOLDOWN_SECONDS),
            )
            return n > 0
        except Exception:
            _LOG.warning("signal cooldown DB fallback to memory")
    return _recent_mem(chain_id, token_address, int(cfg.ALERT_COOLDOWN_SECONDS))


def _mark_cooldown(chain_id: str, token_address: str) -> None:
    _mark_mem(chain_id, token_address, int(cfg.ALERT_COOLDOWN_SECONDS))


def run_alert_dispatch(snapshot: list[dict[str, Any]]) -> None:
    if not cfg.ALERT_DISPATCH_ENABLED:
        return
    for raw in snapshot:
        pipe = raw.get("pipeline")
        profile = raw.get("profile") or {}
        if not isinstance(pipe, dict):
            continue
        cid = str(pipe.get("chain_id") or profile.get("chainId") or "").lower()
        tok = str(pipe.get("token_address") or profile.get("tokenAddress") or "").strip()
        if not cid or not tok:
            continue

        tg = bool(pipe.get("eligible_for_telegram"))
        dc = bool(pipe.get("eligible_for_discord"))
        if not (tg or dc):
            continue

        if _cooldown_active(cid, tok):
            continue

        text = format_signal_message(raw)

        telegram_ok = False
        discord_ok = False

        try:
            if tg:
                r = send_telegram_text(text)
                telegram_ok = bool(not r.get("skipped") and r.get("ok"))
            if dc:
                d = send_discord_webhook(text)
                discord_ok = bool(not d.get("skipped") and d.get("ok"))
            if telegram_ok or discord_ok:
                _mark_cooldown(cid, tok)
                if database_url_configured():
                    try:
                        log_dispatch(
                            chain_id=cid,
                            token_address=tok,
                            rules_version=str(pipe.get("version")),
                            signal_score=float(pipe.get("signal_score") or 0),
                            telegram_ok=telegram_ok,
                            discord_ok=discord_ok,
                            payload={
                                "mvp_gates": pipe.get("mvp_gates_market"),
                                "safety_tier": pipe.get("safety_tier"),
                            },
                        )
                    except Exception as exc:
                        _LOG.warning("dispatch log failed: %s", exc)
        except Exception:
            _LOG.exception("pipeline alert dispatch crashed")
