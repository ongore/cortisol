"""Provider dispatch for token safety snapshots."""

from __future__ import annotations

from typing import Any

import httpx

from cortisol_config import RUCRISK_CRITICAL_SCORE_MIN, SAFETY_FAIL_OPEN
from safety.rugcheck import rugcheck_token_summary, summarize_rugcheck_payload


def evm_stub_bundle(chain_id: str, *, note: str) -> dict[str, Any]:
    return {
        "chain_id": chain_id,
        "provider": "stub",
        "tier": "unknown",
        "blocked_for_trade": False,
        "unreachable": False,
        "gates": {},
        "note": note,
    }


def solana_rugcheck_unreachable(chain_id: str, *, reason: str) -> dict[str, Any]:
    return {
        "chain_id": chain_id,
        "provider": "rugcheck_error",
        "tier": "unknown",
        "blocked_for_trade": not SAFETY_FAIL_OPEN,
        "unreachable": True,
        "gates": {},
        "reason": reason,
    }


async def fetch_safety_bundle(
    client: httpx.AsyncClient,
    *,
    chain_id: str,
    token_address: str,
) -> dict[str, Any]:
    cid = (chain_id or "").strip().lower()
    mint = token_address.strip()

    if cid == "solana":
        rc = await rugcheck_token_summary(client, mint)
        if not rc.get("ok"):
            return solana_rugcheck_unreachable(cid, reason=str(rc.get("error", "rugcheck_failure")))
        raw = rc.get("raw") or {}
        if not isinstance(raw, dict):
            return solana_rugcheck_unreachable(cid, reason="rugcheck_bad_payload")

        fields = summarize_rugcheck_payload(raw)
        agg = fields.get("aggregate_risk_metric")
        critical_metric = agg is not None and float(agg) >= float(RUCRISK_CRITICAL_SCORE_MIN)

        hodl_top = fields.get("top_holder_pct")
        whale_risk = hodl_top is not None and float(hodl_top) > 30.0

        mint_ok = fields.get("mint_authority_renounced")
        freeze_ok = fields.get("freeze_disabled")

        gates = {
            "rug_metric_critical": critical_metric,
            "top_holder_gte_31pct_whale_alert": whale_risk,
            "mint_authority_renounced": mint_ok if mint_ok is not None else None,
            "freeze_disabled": freeze_ok if freeze_ok is not None else None,
        }

        blocked_by_rug = gates["rug_metric_critical"] or gates["top_holder_gte_31pct_whale_alert"]
        tier = "low"
        if blocked_by_rug:
            tier = "high"
        elif agg is not None and agg >= RUCRISK_CRITICAL_SCORE_MIN * 0.6:
            tier = "medium"
        elif mint_ok is False or freeze_ok is False:
            tier = "medium"

        return {
            "chain_id": cid,
            "provider": "rugcheck",
            "tier": tier,
            "blocked_for_trade": blocked_by_rug,
            "unreachable": False,
            "gates": gates,
            "aggregate_risk_metric": agg,
            "derived_summary": fields,
        }

    return evm_stub_bundle(
        cid,
        note="GoPlus/security_scan_not_wired(use_v5_roadmap)",
    )
