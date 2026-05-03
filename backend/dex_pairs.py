"""Dexscreener token-pairs with TTL cache + 429 retries — cuts duplicate traffic and hammering Dex."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

load_dotenv()

_PAIR_CACHE_SECONDS = float(os.getenv("CORTISOL_PAIR_CACHE_SECONDS", "55"))
_PAIR_CACHE_MAX = max(64, int(os.getenv("CORTISOL_PAIR_CACHE_MAX_KEYS", "400")))
_pair_cache: dict[tuple[str, str], tuple[float, list[dict[str, Any]], str | None]] = {}
_pair_lock = asyncio.Lock()


async def fetch_token_pairs(
    client: httpx.AsyncClient,
    chain_id: str,
    token_address: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Cached GET .../token-pairs/v1/{chain}/{token} with small retry/backoff on 429.

    Returns (pairs, fetch_error_message). Cached entries replay without new network IO.
    """
    ch_plain = chain_id.strip().lower()
    raw_tok = token_address.strip()
    tok_plain = raw_tok.lower()
    key = (ch_plain, tok_plain)
    now = time.monotonic()

    async with _pair_lock:
        hit = _pair_cache.get(key)
        if hit is not None and now < hit[0]:
            return list(hit[1]), hit[2]

    ch = quote(ch_plain, safe="")
    tok = quote(raw_tok, safe="")
    url = f"https://api.dexscreener.com/token-pairs/v1/{ch}/{tok}"

    delays = (0.0, 1.1, 2.4)
    data: list[Any] | None = None
    err_detail: str | None = None

    for i, pause in enumerate(delays):
        if pause > 0:
            await asyncio.sleep(pause)
        try:
            response = await client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            raw = response.json()
            data = raw if isinstance(raw, list) else []
            err_detail = None
            break
        except httpx.HTTPStatusError as exc:
            err_detail = f"pairs HTTP {exc.response.status_code}"
            code = exc.response.status_code
            if code == 429 and i < len(delays) - 1:
                continue
            data = []
            break
        except httpx.HTTPError as exc:
            err_detail = str(exc)
            if i < len(delays) - 1:
                continue
            data = []
            break

    if data is None:
        data = []

    deduped = [x for x in data if isinstance(x, dict)]

    async with _pair_lock:
        if len(_pair_cache) >= _PAIR_CACHE_MAX:
            _pair_cache.clear()
        expires = (
            now + _PAIR_CACHE_SECONDS
            if err_detail is None
            else now + min(_PAIR_CACHE_SECONDS, 18.0)
        )
        _pair_cache[key] = (expires, list(deduped), err_detail)

    return list(deduped), err_detail


def clear_pair_cache_for_tests() -> None:
    global _pair_cache

    _pair_cache.clear()
