"""RugCheck public REST (Solana mint reports). Shape-tolerant parsers."""

from __future__ import annotations

from typing import Any

import httpx

from cortisol_config import RUGCHECK_BASE


async def rugcheck_token_summary(client: httpx.AsyncClient, mint: str, *, timeout: float = 5.5) -> dict[str, Any]:
    """
    Fetch summary endpoint. Responses vary; callers must handle missing keys.
    See https://api.rugcheck.xyz/swagger/index.html
    """
    url = f"{RUGCHECK_BASE}/v1/tokens/{mint.strip()}/report/summary"
    try:
        r = await client.get(url, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return {"provider": "rugcheck", "ok": False, "error": "invalid_json_shape"}
        return {"provider": "rugcheck", "ok": True, "raw": data}
    except httpx.HTTPStatusError as exc:
        return {
            "provider": "rugcheck",
            "ok": False,
            "error": f"http_{exc.response.status_code}",
        }
    except httpx.HTTPError as exc:
        return {"provider": "rugcheck", "ok": False, "error": str(exc)}
    except ValueError:
        return {"provider": "rugcheck", "ok": False, "error": "json_decode"}


def _first_num(*vals: Any) -> float | None:
    for v in vals:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        try:
            if isinstance(v, str) and v.strip():
                return float(v)
        except (TypeError, ValueError):
            pass
    return None


def summarize_rugcheck_payload(raw: dict[str, Any] | None) -> dict[str, Any]:
    """
    Derive actionable fields RugCheck-esque APIs often expose under different nesting.
    """
    if raw is None:
        return {}

    risky = float("inf")

    scores: list[float] = []
    for key in ("totalScore", "score", "rugcheckScore"):
        hit = raw.get(key)
        n = _first_num(hit)
        if n is not None:
            scores.append(abs(n))

    risks = raw.get("risks")
    if isinstance(risks, list):
        for r in risks:
            if not isinstance(r, dict):
                continue
            n = _first_num(r.get("score"), r.get("level"))
            if n is not None:
                risky = min(risky, abs(n))

    top_holder = raw.get("topHolderPercentage") or raw.get("top_holder_percentage")
    if isinstance(top_holder, str):
        th = top_holder.replace("%", "")
        tn = _first_num(th)
    else:
        tn = _first_num(top_holder)
    mint_auth = raw.get("mintAuthority") or raw.get("mint_authority") or raw.get("mintAuthorities")
    freeze_auth = raw.get("freezeAuthority") or raw.get("freeze_authority")
    mutable = raw.get("mutableMetadata") or raw.get("mutable_metadata")

    mint_disabled = mint_auth is None or mint_auth in ("", [])
    freeze_disabled = freeze_auth is None or freeze_auth in ("", [])
    resolved_score = scores[0] if scores else None
    worst = risky if risky != float("inf") else None

    merged_risk_metric = resolved_score if worst is None else max(resolved_score or 0, worst)

    return {
        "top_holder_pct": tn,
        "mint_authority_renounced": mint_disabled if mint_auth is not None else None,
        "freeze_disabled": freeze_disabled if freeze_auth is not None else None,
        "mutable_metadata": mutable,
        "aggregate_risk_metric": merged_risk_metric,
    }

