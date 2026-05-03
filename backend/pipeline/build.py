"""Assemble Cortisol MVP pipeline payload (market → safety → stubs → integrations)."""

from __future__ import annotations

from typing import Any

import cortisol_config as cfg
from integrations.buy_links import jupiter_solana_buy_url


def risk_label(signal: float, safety_tier: str) -> str:
    if safety_tier == "high":
        return "high"
    if safety_tier == "medium":
        return "medium"
    if safety_tier == "unknown":
        return "unknown"
    return "medium" if signal < 60 else "low"


def _mvp_market_gates(metrics: dict[str, Any]) -> dict[str, bool]:
    pair_ok = metrics.get("pair_present") is True
    liq = metrics.get("liquidity_usd")
    vol1 = metrics.get("volume_h1")
    buys = metrics.get("buys_h1")
    sells = metrics.get("sells_h1")
    ratio = metrics.get("buy_sell_ratio_h1")

    liquidity_min = isinstance(liq, (int, float)) and float(liq) >= cfg.MIN_LIQ_USD
    volume_ok = isinstance(vol1, (int, float)) and float(vol1) >= cfg.MIN_VOL_H1_USD

    if cfg.REQUIRE_BUYS_GT_SELLS:
        if sells == 0 and isinstance(buys, int) and buys > 0:
            ratio_ok = True
        elif ratio is None:
            ratio_ok = False
        elif isinstance(ratio, (int, float)) and float(ratio) > 1.0:
            ratio_ok = True
        else:
            ratio_ok = False
    else:
        ratio_ok = True

    return {
        "liquidity_usd_gt_min": liquidity_min,
        "volume_h1_usd_gt_min": volume_ok,
        "buy_pressure_gt_sells": ratio_ok,
        "pair_known": pair_ok,
    }


def _signal_components(
    *,
    gates: dict[str, bool],
    safety: dict[str, Any],
) -> tuple[float, float, float]:
    market_score = (_sum_truthy(gates) / max(1, len(gates))) * 100.0 if gates else 0.0

    tier = str(safety.get("tier") or "unknown")
    safety_pts = {
        "low": 100.0,
        "medium": 52.0,
        "high": 5.0,
        "unknown": 58.0,
    }.get(tier, 52.0)
    social_pts = 0.0
    weighted = (
        market_score * 0.58
        + safety_pts * 0.37
        + social_pts * 0.05
    )
    weighted = max(0.0, min(100.0, weighted))
    return weighted, market_score, safety_pts


def _sum_truthy(d: dict[str, bool]) -> float:
    return float(sum(1 for v in d.values() if v))


def assemble_pipeline(
    *,
    profile: dict[str, Any],
    metrics: dict[str, Any],
    safety: dict[str, Any],
    chart_url_fallback: str | None,
    symbol_hint: str | None = None,
) -> dict[str, Any]:
    gates = _mvp_market_gates(metrics)
    market_all_pass = all(gates.values())

    blocked = safety.get("blocked_for_trade") is True
    unreachable = safety.get("unreachable") is True

    if unreachable:
        eligible_trade_alert = market_all_pass and bool(cfg.SAFETY_FAIL_OPEN)
    else:
        eligible_trade_alert = market_all_pass and not blocked

    tg_cfg = bool(cfg.TELEGRAM_BOT_TOKEN and cfg.TELEGRAM_ALERT_CHAT_IDS)
    dc_cfg = bool(cfg.DISCORD_ALERT_WEBHOOK_URL)

    signal, ms, ss_pts = _signal_components(gates=gates, safety=safety)

    cid = str(profile.get("chainId") or "").lower()
    addr = str(profile.get("tokenAddress") or "")
    dex_chart = metrics.get("pair_url") or chart_url_fallback or profile.get("url")

    integrations: dict[str, Any] = {
        "telegram": {"configured": tg_cfg},
        "discord": {"configured": dc_cfg},
        "jupiter": {
            "ready": cid == "solana",
            "swap_preview_url_solana": jupiter_solana_buy_url(addr) if cid == "solana" else None,
            "notes": "v4 swaps via backend quote + Phantom signing",
        },
        "phantom": {
            "browse_template": (
                "https://phantom.app/ul/browse/{encoded_https_target}"
                if cid == "solana"
                else None
            ),
        },
        "helius": {
            "rpc_configured": bool(cfg.HELIUS_RPC_URL),
            "webhooks_notes": "v7 transaction + wallet watchers",
        },
        "birdeye": {"ready": False, "notes": "optional augmentation"},
        "goplus": {"ready": False, "notes": "v5 EVM honeypot + tax scanners"},
        "dexscreener_ws": {"ready": False, "notes": "real-time boosts/CTOs (later)"},
        "dexscreener_http": {"ready": True},
    }

    pipe: dict[str, Any] = {
        "version": cfg.RULES_VERSION,
        "roadmap_targets": ["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8"],
        "mvp_gates_market": gates,
        "market_all_pass": market_all_pass,
        "mvp_gates_safety": safety.get("gates") or {},
        "safety_tier": safety.get("tier"),
        "signal_score": round(signal, 1),
        "score_breakdown": {
            "market_component": round(ms, 1),
            "safety_component": round(ss_pts, 1),
            "social_stub": 0.0,
        },
        "risk_label": risk_label(signal, str(safety.get("tier"))),
        "eligible_for_trade_alert": eligible_trade_alert,
        "eligible_for_telegram": False,
        "eligible_for_discord": False,
        "symbol_hint": symbol_hint,
        "chain_id": cid,
        "token_address": addr,
        "market": {"source": "dexscreener_token_pairs_v1", "metrics": metrics},
        "social": {
            "ready": False,
            "notes": "v6 — X ticker/contract mentions, influencer velocity",
            "x_mentions_last_30m": None,
            "influencer_posts": None,
            "cashtag_velocity": None,
        },
        "safety_bundle": safety,
        "integrations": integrations,
        "actions": {"chart_url": dex_chart},
    }

    dispatch_ok = strict_dispatch_ok(eligible_trade_alert, safety, str(safety.get("tier") or ""))
    pipe["eligible_for_telegram"] = bool(dispatch_ok and tg_cfg and cfg.ALERT_DISPATCH_ENABLED)
    pipe["eligible_for_discord"] = bool(dispatch_ok and dc_cfg and cfg.ALERT_DISPATCH_ENABLED)

    return pipe


def strict_dispatch_ok(
    eligible_trade_alert: bool,
    safety: dict[str, Any],
    safety_tier: str,
) -> bool:
    if not eligible_trade_alert:
        return False
    if not cfg.SAFETY_STRICT:
        return True
    if safety_tier == "unknown" and safety.get("unreachable"):
        return False
    return safety_tier != "high"
