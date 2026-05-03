"""FastAPI service that proxies Dexscreener token-profile data."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from discovery import evaluate_discovery, pick_primary_pair

DEXSCREENER_PROFILES_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
PAIR_FETCH_CONCURRENCY = 12
REQUEST_TIMEOUT = 15.0

app = FastAPI(
    title="Cortisol",
    description="Dexscreener token profiles + pair discovery scoring.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


async def fetch_token_profiles() -> list[dict[str, Any]]:
    """Call the upstream Dexscreener endpoint and return the JSON payload."""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(
                DEXSCREENER_PROFILES_URL,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Dexscreener returned an error: {exc.response.text}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to reach Dexscreener: {exc}",
        ) from exc

    if not isinstance(data, list):
        raise HTTPException(
            status_code=502,
            detail="Unexpected response shape from Dexscreener.",
        )
    return data


async def fetch_token_pairs(
    client: httpx.AsyncClient,
    chain_id: str,
    token_address: str,
) -> list[dict[str, Any]]:
    ch = quote(chain_id.strip().lower(), safe="")
    tok = quote(token_address.strip(), safe="")
    url = f"https://api.dexscreener.com/token-pairs/v1/{ch}/{tok}"
    response = await client.get(url, headers={"Accept": "application/json"})
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list):
        return data
    return []


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "cortisol",
        "status": "ok",
        "docs": "/docs",
        "endpoints": "/feed/with-discovery,/api/feed/with-discovery,/token-profiles/latest",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/token-profiles/latest")
async def get_latest_token_profiles(
    chain_id: str | None = Query(
        default=None,
        description="Filter results by chain (e.g. 'solana', 'ethereum').",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=100,
        description="Maximum number of profiles to return.",
    ),
) -> dict[str, Any]:
    """Return the latest token profiles only (no pair enrichment)."""
    profiles = await fetch_token_profiles()

    if chain_id:
        chain_id_lc = chain_id.lower()
        profiles = [p for p in profiles if p.get("chainId", "").lower() == chain_id_lc]

    if limit is not None:
        profiles = profiles[:limit]

    return {"count": len(profiles), "profiles": profiles}


@app.get("/feed/with-discovery")
@app.get("/api/feed/with-discovery")
async def feed_with_discovery(
    chain_id: str | None = Query(
        default=None,
        description="Filter feed items by chain (e.g. 'solana', 'ethereum').",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=80,
        description="Maximum profiles to enrich (each triggers one pairs lookup).",
    ),
) -> dict[str, Any]:
    """Profiles merged with primary pair snapshot + discovery rubric."""
    profiles = await fetch_token_profiles()

    if chain_id:
        cid = chain_id.lower()
        profiles = [p for p in profiles if p.get("chainId", "").lower() == cid]

    if limit is not None:
        profiles = profiles[:limit]

    sem = asyncio.Semaphore(PAIR_FETCH_CONCURRENCY)
    items: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:

        async def one(profile: dict[str, Any]) -> dict[str, Any]:
            cid = str(profile.get("chainId") or "")
            addr = str(profile.get("tokenAddress") or "")
            pair_json: dict[str, Any] | None = None
            pairs_raw: list[dict[str, Any]] = []
            err: str | None = None
            async with sem:
                try:
                    pairs_raw = await fetch_token_pairs(client, cid, addr)
                    pair_json = pick_primary_pair(pairs_raw, addr)
                except httpx.HTTPStatusError as exc:
                    err = f"pairs HTTP {exc.response.status_code}"
                    pair_json = None
                except httpx.HTTPError as exc:
                    err = str(exc)
                    pair_json = None

            discovery = evaluate_discovery(pair_json)
            slim_pair = None
            if pair_json:
                slim_pair = {
                    "chainId": pair_json.get("chainId"),
                    "dexId": pair_json.get("dexId"),
                    "pairAddress": pair_json.get("pairAddress"),
                    "url": pair_json.get("url"),
                    "priceUsd": pair_json.get("priceUsd"),
                    "liquidity": pair_json.get("liquidity"),
                    "volume": pair_json.get("volume"),
                    "txns": pair_json.get("txns"),
                    "priceChange": pair_json.get("priceChange"),
                    "fdv": pair_json.get("fdv"),
                    "marketCap": pair_json.get("marketCap"),
                    "pairCreatedAt": pair_json.get("pairCreatedAt"),
                    "baseToken": pair_json.get("baseToken"),
                    "quoteToken": pair_json.get("quoteToken"),
                }

            return {
                "profile": profile,
                "pair": slim_pair,
                "pairs_found": len(pairs_raw),
                "pair_fetch_error": err,
                "discovery": discovery,
            }

        items = await asyncio.gather(*[one(p) for p in profiles])

    bad_items = sum(1 for it in items if it["discovery"]["overall_bad"])
    return {
        "count": len(items),
        "bad_count": bad_items,
        "items": items,
    }


@app.get("/token-profiles/latest/{token_address}")
async def get_token_profile_by_address(token_address: str) -> dict[str, Any]:
    """Return a single token profile matching the given token address."""
    profiles = await fetch_token_profiles()
    target = token_address.lower()
    for profile in profiles:
        if profile.get("tokenAddress", "").lower() == target:
            return profile
    raise HTTPException(
        status_code=404,
        detail=f"Token address '{token_address}' not found in latest profiles.",
    )
