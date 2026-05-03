"""Plain-text payloads for Telegram + Discord webhook."""

from __future__ import annotations

from typing import Any


def format_signal_message(item: dict[str, Any]) -> str:
    """Readable alert body (plain text — parse_mode off on Telegram API)."""

    pipe = item.get("pipeline") or {}
    profile = item.get("profile") or {}
    cid = pipe.get("chain_id") or profile.get("chainId") or ""
    addr = pipe.get("token_address") or profile.get("tokenAddress") or ""

    dex = pipe.get("actions", {}).get("chart_url") or profile.get("url")
    ij = pipe.get("integrations", {}).get("jupiter", {}).get("swap_preview_url_solana")
    gm = pipe.get("mvp_gates_market") or {}
    gates_line = ", ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in sorted(gm.items(), key=lambda x: x[0]))
    agg = pipe.get("safety_bundle", {}).get("aggregate_risk_metric")

    chunks = [
        "CORTISOL · SURVEILLANCE MVP",
        f"{str(cid).upper()} {addr}",
        f"SIGNAL_SCORE · {pipe.get('signal_score')} / risk_label · {pipe.get('risk_label')}",
        "",
        "MVP market gates:",
        gates_line,
        "",
        f"Safety tier · {pipe.get('safety_tier')} · rug_metric · {agg}",
        f"Eligible trade alert · {pipe.get('eligible_for_trade_alert')}",
        f"Rules `{pipe.get('version')}`",
    ]

    if dex:
        chunks += ["", f"Dex chart · {dex}"]
    if ij:
        chunks += ["", f"Swap preview · {ij}"]
    chunks += ["", "(Not financial advice)"]
    return "\n".join(chunks)[:3950]

