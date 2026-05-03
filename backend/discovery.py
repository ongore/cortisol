"""Primary pair picker for Dex snapshots (discovery rubric legacy entrypoint retired)."""

from __future__ import annotations

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
