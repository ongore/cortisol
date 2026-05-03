"""Map pipeline output into legacy DiscoveryResult shape for SPA compatibility."""

from __future__ import annotations

from typing import Any


import cortisol_config as cfg


def _frontend_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    m = dict(metrics)
    m.pop("pair_present", None)
    return m


def discovery_from_pipeline(pipeline: dict[str, Any]) -> dict[str, Any]:
    """Produce `discovery` object matching existing React types."""

    metrics_raw = pipeline.get("market", {}).get("metrics") or {}
    metrics = _frontend_metrics(metrics_raw)
    gates: dict[str, bool] = pipeline.get("mvp_gates_market") or {}
    safety = pipeline.get("safety_bundle") or {}

    flags: list[dict[str, Any]] = []
    positives: list[dict[str, Any]] = []

    def label_for_gate(key: str) -> str:
        return {
            "liquidity_usd_gt_min": f"LIQUIDITY ≥ ${int(cfg.MIN_LIQ_USD):,}",
            "volume_h1_usd_gt_min": f"VOL h1 ≥ ${int(cfg.MIN_VOL_H1_USD):,}",
            "buy_pressure_gt_sells": "BUYS > SELLS",
            "pair_known": "PAIR DATA",
        }.get(key, key)

    if not gates.get("pair_known"):
        flags.append({"severity": "bad", "key": "pair_known", "label": "FAIL · PAIR DATA"})
    else:
        if not gates.get("liquidity_usd_gt_min"):
            flags.append(
                {
                    "severity": "warn",
                    "key": "liquidity_usd_gt_min",
                    "label": f"FAIL · {label_for_gate('liquidity_usd_gt_min')}",
                },
            )
        if not gates.get("volume_h1_usd_gt_min"):
            flags.append(
                {
                    "severity": "bad",
                    "key": "volume_h1_usd_gt_min",
                    "label": f"FAIL · {label_for_gate('volume_h1_usd_gt_min')}",
                },
            )
        if not gates.get("buy_pressure_gt_sells"):
            flags.append(
                {
                    "severity": "warn",
                    "key": "buy_pressure_gt_sells",
                    "label": f"FAIL · {label_for_gate('buy_pressure_gt_sells')}",
                },
            )

    market_all = pipeline.get("market_all_pass") is True

    reachable = safety.get("unreachable") is not True
    if reachable and safety.get("blocked_for_trade"):
        tier = str(safety.get("tier")).upper()
        severity = "bad" if tier == "HIGH" else "warn"
        flags.append({"severity": severity, "key": "safety", "label": f"SAFETY {tier}"})

    elif safety.get("unreachable"):
        flags.append(
            {"severity": "warn", "key": "safety_unreachable", "label": "RUGCHECK OFFLINE/STUB"},
        )

    for key, ok in gates.items():
        if ok:
            positives.append({"key": key, "label": f"PASS · {label_for_gate(key)}"})

    signal = pipeline.get("signal_score")
    if isinstance(signal, (int, float)) and float(signal) >= 70:
        positives.append({"key": "signal", "label": f"COMPOSITE {signal}"})

    bad_count = sum(1 for f in flags if f["severity"] == "bad")
    warn_count = sum(1 for f in flags if f["severity"] == "warn")

    tier = safety.get("tier")
    blocked = safety.get("blocked_for_trade") is True

    overall_bad = (not market_all) or (reachable and blocked and tier == "high")

    if not overall_bad and bad_count > 0:
        overall_bad = True

    if overall_bad:
        summary = "BAD"
    elif warn_count > 0 or tier in ("medium", "unknown"):
        summary = "WARN"
    else:
        summary = "OK"

    return {
        "overall_bad": overall_bad,
        "bad_count": bad_count,
        "warn_count": warn_count,
        "metrics": metrics,
        "flags": flags[:20],
        "positives": positives[:14],
        "summary": summary,
    }

