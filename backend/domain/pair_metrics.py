"""Extract normalized market metrics from a Dexscreener pair snapshot."""

from __future__ import annotations

import time
from typing import Any


def _num(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def compute_pair_metrics(
    pair: dict[str, Any] | None,
    *,
    now_ms: float | None = None,
) -> dict[str, Any]:
    """Return the same canonical metrics shape the UI consumes (discovery.metrics-compatible)."""

    now_ms = now_ms if now_ms is not None else time.time() * 1000

    empty: dict[str, Any] = {
        "liquidity_usd": None,
        "volume_h1": None,
        "volume_h24": None,
        "txns_h1_total": None,
        "buys_h1": None,
        "sells_h1": None,
        "buy_sell_ratio_h1": None,
        "pair_age_hours": None,
        "pair_age_days": None,
        "fdv": None,
        "market_cap": None,
        "price_change_m5": None,
        "price_change_h1": None,
        "dex_id": None,
        "pair_address": None,
        "pair_url": None,
        "pair_present": False,
    }

    if not pair:
        return empty

    liq_block = pair.get("liquidity")
    liq_usd = None
    if isinstance(liq_block, dict):
        liq_usd = _num(liq_block.get("usd"))

    vol_block = pair.get("volume") or {}
    vol_h1 = _num(vol_block.get("h1"))
    vol_h24 = _num(vol_block.get("h24"))

    tx_h1 = (pair.get("txns") or {}).get("h1") or {}
    buys_h1 = int(tx_h1.get("buys") or 0)
    sells_h1 = int(tx_h1.get("sells") or 0)
    tx_total = buys_h1 + sells_h1

    if sells_h1 > 0:
        ratio = buys_h1 / sells_h1
    elif buys_h1 > 0:
        ratio = None
    else:
        ratio = 0.0

    age_hours = None
    age_days = None
    created = pair.get("pairCreatedAt")
    if created is not None:
        try:
            age_ms = float(now_ms) - float(created)
            age_hours = max(0.0, age_ms / (1000 * 3600))
            age_days = age_hours / 24
        except (TypeError, ValueError):
            pass

    fdv = _num(pair.get("fdv"))
    mcap = _num(pair.get("marketCap"))
    pc = pair.get("priceChange") or {}
    m5 = _num(pc.get("m5"))
    h1_pc = _num(pc.get("h1"))

    metrics = dict(empty)
    metrics.update(
        {
            "pair_present": True,
            "liquidity_usd": liq_usd,
            "volume_h1": vol_h1,
            "volume_h24": vol_h24,
            "txns_h1_total": tx_total,
            "buys_h1": buys_h1,
            "sells_h1": sells_h1,
            "buy_sell_ratio_h1": ratio,
            "pair_age_hours": age_hours,
            "pair_age_days": age_days,
            "fdv": fdv,
            "market_cap": mcap,
            "price_change_m5": m5,
            "price_change_h1": h1_pc,
            "dex_id": pair.get("dexId"),
            "pair_address": pair.get("pairAddress"),
            "pair_url": pair.get("url"),
        },
    )
    return metrics
