"""Merge several Dexscreener token lists so the feed is not stuck on `/latest` (~30 tokens)."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

# (debug_name, url, tie_rank) — on equal freshness, lower tie_rank lists win (shown first).
DEX_PROFILE_SOURCES: tuple[tuple[str, str, int], ...] = (
    ("recent_updates", "https://api.dexscreener.com/token-profiles/recent-updates/v1", 0),
    ("boosts_latest", "https://api.dexscreener.com/token-boosts/latest/v1", 1),
    ("boosts_top", "https://api.dexscreener.com/token-boosts/top/v1", 2),
    ("community_takeovers", "https://api.dexscreener.com/community-takeovers/latest/v1", 3),
    ("ads_latest", "https://api.dexscreener.com/ads/latest/v1", 4),
    ("profiles_latest", "https://api.dexscreener.com/token-profiles/latest/v1", 5),
)

PROFILES_LATEST_URL = "https://api.dexscreener.com/token-profiles/latest/v1"

_CACHE_SECONDS = float(os.getenv("CORTISOL_PROFILE_CACHE_SECONDS", "55"))
_CACHE_SECONDS_EMPTY = float(os.getenv("CORTISOL_PROFILE_CACHE_EMPTY_SECONDS", "12"))
# Pause between Dex *list* calls to stay under free-tier burst limits (seconds).
_DEX_LIST_PAUSE = float(os.getenv("CORTISOL_DEX_LIST_PAUSE_SECONDS", "1.1"))
# Extra wait before latest-only fallback after an empty merge.
_FALLBACK_COOLDOWN = float(os.getenv("CORTISOL_DEX_FALLBACK_COOLDOWN_SECONDS", "2.0"))

_cache_lock = asyncio.Lock()
_profiles_cache: list[dict[str, Any]] | None = None
_meta_cache: dict[str, Any] | None = None
_cache_mono_expiry: float = 0.0


def profile_key(row: dict[str, Any]) -> tuple[str, str] | None:
    cid = str(row.get("chainId") or "").strip().lower()
    tok = str(row.get("tokenAddress") or "").strip().lower()
    if not cid or not tok:
        return None
    return (cid, tok)


def dedupe_profiles_preserve_order(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicate rows for the same (chainId, tokenAddress), keeping sort order intact."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for p in profiles:
        pk = profile_key(p)
        if pk is None or pk in seen:
            continue
        seen.add(pk)
        out.append(p)
    return out


def _parse_iso_ts(raw: Any) -> float | None:
    if raw is None or not isinstance(raw, str):
        return None
    s = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def row_freshness_epoch(row: dict[str, Any]) -> float:
    """Best-effort recency from fields present on different Dex list types."""
    best = 0.0
    for k in ("updatedAt", "claimDate", "date"):
        ts = _parse_iso_ts(row.get(k))
        if ts is not None:
            best = max(best, ts)
    return best


def _merge_fields(dst: dict[str, Any], src: dict[str, Any]) -> None:
    """Fill empty / missing visual & metadata from another source row."""
    for sk, sv in src.items():
        if sv is None:
            continue
        if sk not in dst or dst[sk] in (None, "", [], {}):
            dst[sk] = sv


async def fetch_json_list(
    client: httpx.AsyncClient,
    url: str,
) -> list[dict[str, Any]]:
    response = await client.get(url, headers={"Accept": "application/json"})
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


async def fetch_json_list_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    label: str,
    upstream_errors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Retry a few times on 429; record last error on total failure."""
    backoff = (0.0, 1.25, 2.75)
    last_detail: str | None = None
    for i, pause in enumerate(backoff):
        if pause > 0:
            await asyncio.sleep(pause)
        try:
            return await fetch_json_list(client, url)
        except httpx.HTTPStatusError as exc:
            last_detail = f"{label}: HTTP {exc.response.status_code} {exc.response.text[:200]}"
            if exc.response.status_code == 429 and i < len(backoff) - 1:
                continue
            upstream_errors.append({"source": label, "detail": last_detail[:300]})
            return []
        except httpx.HTTPError as exc:
            last_detail = f"{label}: {exc}"
            if i < len(backoff) - 1:
                continue
            upstream_errors.append({"source": label, "detail": (last_detail or "")[:300]})
            return []
        except Exception as exc:  # noqa: BLE001
            upstream_errors.append({"source": label, "detail": str(exc)[:300]})
            return []


def _assemble_merge(raw_lists: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    freshness: dict[tuple[str, str], float] = {}
    tie: dict[tuple[str, str], int] = {}

    for (_name, _url, rank), rows in zip(DEX_PROFILE_SOURCES, raw_lists):
        for row in rows:
            key = profile_key(row)
            if key is None:
                continue
            fr = row_freshness_epoch(row)
            if key not in merged:
                merged[key] = dict(row)
                freshness[key] = fr
                tie[key] = rank
            else:
                _merge_fields(merged[key], row)
                freshness[key] = max(freshness[key], fr)
                tie[key] = min(tie[key], rank)

    profiles = list(merged.values())

    def sort_key(p: dict[str, Any]) -> tuple[float, int, str]:
        k = profile_key(p)
        if not k:
            return (0.0, 99, "")
        return (-freshness.get(k, 0.0), tie.get(k, 99), k[1])

    profiles.sort(key=sort_key)
    return profiles


async def _fetch_merged_uncached(client: httpx.AsyncClient) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    upstream_errors: list[dict[str, str]] = []
    raw_lists: list[list[dict[str, Any]]] = []

    for i, (name, url, _) in enumerate(DEX_PROFILE_SOURCES):
        if i > 0 and _DEX_LIST_PAUSE > 0:
            await asyncio.sleep(_DEX_LIST_PAUSE)
        rows = await fetch_json_list_with_retries(client, url, label=name, upstream_errors=upstream_errors)
        raw_lists.append(rows)

    profiles = _assemble_merge(raw_lists)

    meta: dict[str, Any] = {
        "source_endpoints": len(DEX_PROFILE_SOURCES),
        "unique_tokens": len(profiles),
        "sources_failed": len(upstream_errors),
        "upstream_errors": upstream_errors or None,
        "fallback": None,
    }
    return profiles, meta


async def _fetch_profiles_latest_only(
    client: httpx.AsyncClient,
    *,
    upstream_errors: list[dict[str, str]] | None,
) -> list[dict[str, Any]]:
    errs = upstream_errors if upstream_errors is not None else []
    return await fetch_json_list_with_retries(
        client,
        PROFILES_LATEST_URL,
        label="profiles_latest_standalone",
        upstream_errors=errs,
    )


async def fetch_merged_token_profiles(client: httpx.AsyncClient) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Returned list is merged from several Dexscreener buckets (beyond `/latest`'s ~30 rows).

    Cached briefly so the UI polling does not hammer Dex. Uses pauses / retries on 429,
    stale cache, then `/profiles/latest` only before giving up empty.
    """
    global _profiles_cache, _meta_cache, _cache_mono_expiry

    now = time.monotonic()
    async with _cache_lock:
        if (
            _profiles_cache is not None
            and _meta_cache is not None
            and now < _cache_mono_expiry
        ):
            return list(_profiles_cache), dict(_meta_cache)

        prior_profiles = list(_profiles_cache) if _profiles_cache else None

        profiles, meta = await _fetch_merged_uncached(client)

        if not profiles and prior_profiles:
            meta = dict(meta)
            meta["fallback"] = "stale_cache_upstream_empty"
            meta["unique_tokens"] = len(prior_profiles)
            profiles = prior_profiles
        elif not profiles:
            await asyncio.sleep(_FALLBACK_COOLDOWN)
            fb_errs: list[dict[str, str]] = list(meta.get("upstream_errors") or [])
            standalone = await _fetch_profiles_latest_only(client, upstream_errors=fb_errs)
            meta = dict(meta)
            meta["upstream_errors"] = fb_errs or None
            if standalone:
                meta["fallback"] = "profiles_latest_only"
                meta["unique_tokens"] = len(standalone)
                profiles = standalone
            elif prior_profiles:
                meta["fallback"] = "stale_cache_after_standalone_failed"
                meta["unique_tokens"] = len(prior_profiles)
                profiles = prior_profiles
                meta["sources_failed"] = len(fb_errs)

        profiles = dedupe_profiles_preserve_order(profiles)
        meta = dict(meta)
        meta["unique_tokens"] = len(profiles)

        ttl = _CACHE_SECONDS if profiles else _CACHE_SECONDS_EMPTY

        if profiles:
            _profiles_cache = list(profiles)
            _meta_cache = dict(meta)

        _cache_mono_expiry = now + ttl

        return list(profiles), dict(meta)


def clear_profile_cache_for_tests() -> None:
    global _profiles_cache, _meta_cache, _cache_mono_expiry

    _profiles_cache = None
    _meta_cache = None
    _cache_mono_expiry = 0.0
