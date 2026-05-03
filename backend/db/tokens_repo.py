"""Upsert Dex token observations (merged profile / discovery feed)."""

from __future__ import annotations

from typing import Any

from db.connection import db_connection

_UPSERT_SQL = """
INSERT INTO dex_tokens (
  chain_id, token_address, symbol, pair_address
) VALUES (
  %(chain_id)s, %(token_address)s, %(symbol)s, %(pair_address)s
)
ON CONFLICT (chain_id, token_address) DO UPDATE SET
  last_seen_at = NOW(),
  seen_count = dex_tokens.seen_count + 1,
  symbol = COALESCE(EXCLUDED.symbol, dex_tokens.symbol),
  pair_address = COALESCE(EXCLUDED.pair_address, dex_tokens.pair_address);
"""


_LIST_SQL = """
SELECT
  chain_id,
  token_address,
  symbol,
  pair_address,
  seen_count,
  first_seen_at,
  last_seen_at
FROM dex_tokens
ORDER BY last_seen_at DESC
LIMIT %(limit)s;
"""


def _norm_chain_addr(profile: dict[str, Any]) -> tuple[str, str] | None:
    cid = str(profile.get("chainId") or "").strip().lower()
    addr = str(profile.get("tokenAddress") or "").strip().lower()
    if not cid or not addr:
        return None
    return cid, addr


def rows_from_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for p in profiles:
        ids = _norm_chain_addr(p)
        if not ids:
            continue
        cid, addr = ids
        sym_raw = p.get("symbol") or p.get("ticker")
        sym = str(sym_raw).strip() if sym_raw is not None else None
        if not sym:
            sym = None
        row = {"chain_id": cid, "token_address": addr, "symbol": sym, "pair_address": None}
        k = (cid, addr)
        if k not in out:
            out[k] = row
        elif sym and not out[k]["symbol"]:
            out[k]["symbol"] = sym
    return list(out.values())


def rows_from_discovery_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for it in items:
        prof = it.get("profile") or {}
        ids = _norm_chain_addr(prof)
        if not ids:
            continue
        cid, addr = ids
        sym_raw = prof.get("symbol") or prof.get("ticker")
        sym = str(sym_raw).strip() if sym_raw is not None else None
        if not sym:
            sym = None
        pair = it.get("pair") or {}
        pair_addr = pair.get("pairAddress")
        pair_s = str(pair_addr).strip() if pair_addr else None
        if not pair_s:
            pair_s = None
        k = (cid, addr)
        prev = out.get(k)
        if prev is None:
            out[k] = {
                "chain_id": cid,
                "token_address": addr,
                "symbol": sym,
                "pair_address": pair_s,
            }
        else:
            if sym and not prev["symbol"]:
                prev["symbol"] = sym
            if pair_s and not prev["pair_address"]:
                prev["pair_address"] = pair_s
    return list(out.values())


def upsert_dex_token_rows(rows: list[dict[str, Any]]) -> int:
    """Upsert each row; returns number of statements executed."""
    if not rows:
        return 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(_UPSERT_SQL, rows)
        conn.commit()
    return len(rows)


def list_dex_tokens_recent(limit: int) -> list[dict[str, Any]]:
    # API + webhook broadcast share this; clamp high for watch-sized lists.
    limit = max(1, min(3000, int(limit)))
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_LIST_SQL, {"limit": limit})
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
