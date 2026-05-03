"""Evaluate Dexscreener pair snapshots against discovery rubric."""

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


def pick_primary_pair(
    pairs: list[dict[str, Any]],
    token_address: str,
) -> dict[str, Any] | None:
    """Prefer pairs whose base token matches; rank by liquidity USD then volume h1."""
    if not pairs:
        return None
    want = token_address.lower()
    relevant = [
        p
        for p in pairs
        if str((p.get("baseToken") or {}).get("address", "")).lower() == want
    ]
    pool = relevant if relevant else pairs

    def score(p: dict[str, Any]) -> tuple[float, float]:
        lb = p.get("liquidity")
        liq = _num(lb.get("usd")) if isinstance(lb, dict) else None
        vol = _num((p.get("volume") or {}).get("h1"))
        return (liq if liq is not None else -1.0, vol if vol is not None else -1.0)

    return max(pool, key=score)


def evaluate_discovery(
    pair: dict[str, Any] | None,
    *,
    now_ms: float | None = None,
) -> dict[str, Any]:
    now_ms = now_ms if now_ms is not None else time.time() * 1000
    flags: list[dict[str, Any]] = []
    positives: list[dict[str, Any]] = []

    metrics: dict[str, Any] = {
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
    }

    if not pair:
        flags.append({"severity": "bad", "key": "pair", "label": "NO PAIR DATA"})
        return {
            "overall_bad": True,
            "bad_count": 1,
            "warn_count": 0,
            "metrics": metrics,
            "flags": flags,
            "positives": positives,
            "summary": "BAD",
        }

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

    metrics.update(
        {
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

    # --- Liquidity ---
    if liq_usd is None:
        flags.append({"severity": "warn", "key": "liquidity", "label": "LIQ UNKNOWN"})
    elif liq_usd < 10_000:
        flags.append({"severity": "bad", "key": "liquidity", "label": "LIQ < $10k"})
    elif liq_usd < 20_000:
        flags.append({"severity": "warn", "key": "liquidity", "label": "LIQ < $20k"})
    elif 30_000 <= liq_usd <= 150_000:
        positives.append({"key": "liquidity", "label": "LIQ SWEET"})
    elif liq_usd > 500_000:
        flags.append({"severity": "warn", "key": "liquidity", "label": "LIQ > $500k"})

    # --- Volume (last hour USD) ---
    if vol_h1 is None:
        flags.append({"severity": "warn", "key": "volume", "label": "VOL UNKNOWN"})
    elif vol_h1 < 10_000:
        flags.append({"severity": "bad", "key": "volume", "label": "VOL h1 < $10k"})
    elif vol_h1 < 50_000:
        flags.append({"severity": "warn", "key": "volume", "label": "VOL h1 < $50k"})
    elif 100_000 <= vol_h1 <= 500_000:
        positives.append({"key": "volume", "label": "VOL STRONG"})
    elif vol_h1 >= 1_000_000:
        positives.append({"key": "volume", "label": "VOL EXPLOSIVE"})

    # --- Transactions (h1) ---
    if tx_total < 50:
        flags.append({"severity": "bad", "key": "txns", "label": "TX h1 < 50"})
    elif tx_total < 100:
        flags.append({"severity": "warn", "key": "txns", "label": "TX h1 < 100"})
    elif 300 <= tx_total <= 1000:
        positives.append({"key": "txns", "label": "TX STRONG"})
    elif tx_total > 1000:
        positives.append({"key": "txns", "label": "TX HOT"})

    # --- Buy / sell ratio ---
    if sells_h1 > 0:
        if ratio < 1.0:
            flags.append({"severity": "bad", "key": "ratio", "label": "BUYS < SELLS"})
        elif ratio < 1.2:
            flags.append({"severity": "warn", "key": "ratio", "label": "RATIO < 1.2"})
        elif 1.5 <= ratio <= 2.5:
            positives.append({"key": "ratio", "label": "RATIO STRONG"})
        if sells_h1 >= buys_h1 * 2 and sells_h1 >= 10:
            flags.append({"severity": "warn", "key": "sells", "label": "SELL SPIKE"})
    elif buys_h1 > 0:
        positives.append({"key": "ratio", "label": "NO SELLS h1"})

    # --- Pair age ---
    if age_days is not None:
        if age_days > 5:
            flags.append({"severity": "bad", "key": "age", "label": "PAIR > 5d"})
        elif age_days > 3:
            flags.append({"severity": "warn", "key": "age", "label": "PAIR > 3d"})
    if age_hours is not None:
        if age_hours >= (10 / 60) and age_hours <= 12:
            positives.append({"key": "age", "label": "AGE IDEAL"})
        if age_hours >= 0.5 and age_hours <= 4:
            positives.append({"key": "age", "label": "AGE SWEET"})

    # --- FDV ---
    if fdv is not None:
        if fdv > 20_000_000:
            flags.append({"severity": "bad", "key": "fdv", "label": "FDV > $20M"})
        elif 100_000 <= fdv <= 2_000_000:
            positives.append({"key": "fdv", "label": "FDV EARLY"})
        elif 500_000 <= fdv <= 10_000_000:
            positives.append({"key": "fdv", "label": "FDV GOOD RANGE"})
        elif fdv < 100_000:
            flags.append({"severity": "warn", "key": "fdv", "label": "FDV MICRO"})

    if fdv is not None and liq_usd is not None:
        if fdv >= 5_000_000 and liq_usd < 50_000:
            flags.append({"severity": "warn", "key": "fdv_liq", "label": "HIGH FDV / LOW LIQ"})

    # --- Price change ---
    if m5 is not None:
        if m5 >= 300:
            flags.append({"severity": "bad", "key": "price_m5", "label": "M5 ≥ +300%"})
        elif 5 <= m5 <= 20:
            positives.append({"key": "price_m5", "label": "M5 SWEET"})
        elif m5 <= -25:
            flags.append({"severity": "warn", "key": "price_m5", "label": "M5 DUMP"})
    if h1_pc is not None:
        if 20 <= h1_pc <= 100:
            positives.append({"key": "price_h1", "label": "H1 SWEET"})
        elif h1_pc >= 300:
            flags.append({"severity": "warn", "key": "price_h1", "label": "H1 EXTREME"})
        elif h1_pc <= -40:
            flags.append({"severity": "warn", "key": "price_h1", "label": "H1 DUMP"})

    bad_count = sum(1 for f in flags if f["severity"] == "bad")
    warn_count = sum(1 for f in flags if f["severity"] == "warn")
    overall_bad = bad_count > 0

    summary = "BAD" if overall_bad else ("WARN" if warn_count else "OK")

    return {
        "overall_bad": overall_bad,
        "bad_count": bad_count,
        "warn_count": warn_count,
        "metrics": metrics,
        "flags": flags,
        "positives": positives,
        "summary": summary,
    }
