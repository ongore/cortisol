"""
Periodic Dex snapshots for `dex_tokens` → your HTTP endpoint (outbound "webhook").

This is polling + batch POST, not Dexscreener inbound webhooks. Large N + short intervals
risk HTTP 429 on Dex — prefer smaller watchlists, higher interval, or Helius/streaming later.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

import cortisol_config as cfg
from db.connection import database_url_configured
from db.tokens_repo import list_dex_tokens_recent
from dex_pairs import fetch_token_pairs
from discovery import pick_primary_pair
from domain.pair_metrics import compute_pair_metrics

_LOG = logging.getLogger("cortisol.broadcast")

_busy = False


def _jsonify_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


async def _build_snapshots(
    client: httpx.AsyncClient,
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    sem = asyncio.Semaphore(cfg.BROADCAST_PAIR_CONCURRENCY)

    async def doit(row: dict[str, Any]) -> dict[str, Any]:
        cid = str(row.get("chain_id") or "").strip().lower()
        tok = str(row.get("token_address") or "").strip()
        base = _jsonify_row(row)
        if not cid or not tok:
            return {**base, "_error": "bad_row"}
        async with sem:
            pairs_raw, ferr = await fetch_token_pairs(client, cid, tok)
        pair_json = pick_primary_pair(pairs_raw, tok)
        metrics = compute_pair_metrics(pair_json)
        slim = {k: v for k, v in metrics.items() if v is not None}
        return {**base, "pair_fetch_error": ferr, "metrics": slim}

    raw = await asyncio.gather(*(doit(r) for r in rows), return_exceptions=True)
    out: list[dict[str, Any]] = []
    err_n = 0
    for slot in raw:
        if isinstance(slot, BaseException):
            err_n += 1
            _LOG.warning("snapshot task failed: %s", slot)
            out.append({"_error": repr(slot)})
            continue
        out.append(slot)
    return out, err_n


async def run_watchlist_broadcast_tick() -> dict[str, Any] | None:
    if not database_url_configured():
        _LOG.debug("watchlist broadcast: no Postgres URI (DATABASE_URL / SUPABASE_DATABASE_URL)")
        return None
    if not cfg.OUTBOUND_WATCHLIST_WEBHOOK_URL:
        return None

    rows = await asyncio.to_thread(list_dex_tokens_recent, cfg.BROADCAST_WATCHLIST_TOKEN_LIMIT)
    if not rows:
        return {
            "kind": "dex_tokens_watch_snapshots",
            "rules_version": cfg.RULES_VERSION,
            "generated_at_unix": time.time(),
            "row_count_loaded": 0,
            "snapshots": [],
            "partial_errors": 0,
        }

    timeout = httpx.Timeout(45.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        snaps, err_n = await _build_snapshots(client, rows)

    return {
        "kind": "dex_tokens_watch_snapshots",
        "rules_version": cfg.RULES_VERSION,
        "generated_at_unix": time.time(),
        "requested_limit": cfg.BROADCAST_WATCHLIST_TOKEN_LIMIT,
        "row_count_loaded": len(rows),
        "partial_errors": err_n,
        "snapshots": snaps,
    }


async def _post_payload(body: dict[str, Any]) -> None:
    url = cfg.OUTBOUND_WATCHLIST_WEBHOOK_URL
    if not url:
        return
    headers: dict[str, str] = {"Content-Type": "application/json", "User-Agent": "cortisol-broadcast/1"}
    if cfg.OUTBOUND_WATCHLIST_WEBHOOK_SECRET:
        headers["X-Cortisol-Secret"] = cfg.OUTBOUND_WATCHLIST_WEBHOOK_SECRET
    wt = httpx.Timeout(90.0)
    async with httpx.AsyncClient(timeout=wt) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()


async def periodic_watchlist_webhook_loop() -> None:
    global _busy  # noqa: PLW0603

    if not cfg.OUTBOUND_WATCHLIST_WEBHOOK_URL:
        return
    if cfg.BROADCAST_WATCHLIST_SECONDS <= 0:
        return

    interval = float(cfg.BROADCAST_WATCHLIST_SECONDS)
    _LOG.info(
        "Watchlist outbound webhook: interval ~%.2fs, max %s tokens (Dex pairs; overlaps skipped)",
        interval,
        cfg.BROADCAST_WATCHLIST_TOKEN_LIMIT,
    )

    while True:
        try:
            await asyncio.sleep(interval)
            if _busy:
                _LOG.debug("watchlist webhook: skip — previous tick still running")
                continue
            _busy = True
            try:
                payload = await run_watchlist_broadcast_tick()
                if payload is None:
                    continue
                await _post_payload(payload)
            finally:
                _busy = False
        except asyncio.CancelledError:
            raise
        except httpx.HTTPStatusError as exc:
            _LOG.warning(
                "watchlist webhook POST failed: HTTP %s — %s",
                exc.response.status_code,
                exc.response.text[:240],
            )
        except Exception:
            _LOG.exception("watchlist webhook tick failed")
