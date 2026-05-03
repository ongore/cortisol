"""FastAPI service that proxies Dexscreener token-profile data."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import asyncio
import logging
import os
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from discovery import pick_primary_pair
from dex_pairs import fetch_token_pairs
from feed_sources import fetch_merged_token_profiles

from alerts.pipeline_dispatch import run_alert_dispatch
from cortisol_config import (
    BROADCAST_WATCHLIST_SECONDS,
    FEED_MATH_PASS_ONLY,
    OUTBOUND_WATCHLIST_WEBHOOK_URL,
    SAFETY_FETCH_CONCURRENCY,
)
from db.alerts_repo import insert_alert_row, list_alerts_recent
from db.connection import (
    database_missing_detail,
    database_url_configured,
    db_health_sync,
)
from db.tokens_repo import (
    list_dex_tokens_recent,
    rows_from_discovery_items,
    rows_from_profiles,
    upsert_dex_token_rows,
)
from domain.pair_metrics import compute_pair_metrics
from pipeline.build import assemble_pipeline
from pipeline.discovery_compat import discovery_from_pipeline
from safety.fetch import fetch_safety_bundle

_LOG = logging.getLogger("cortisol")


def _token_logging_enabled() -> bool:
    v = os.getenv("CORTISOL_LOG_TOKENS_TO_DB", "1").strip().lower()
    return v not in ("", "0", "false", "no", "off")


def _bg_log_profiles(profiles_snapshot: list[dict[str, Any]]) -> None:
    if not database_url_configured() or not _token_logging_enabled():
        return
    try:
        rows = rows_from_profiles(profiles_snapshot)
        if rows:
            upsert_dex_token_rows(rows)
    except Exception:  # noqa: BLE001
        _LOG.exception("dex_tokens: upsert after /token-profiles/latest failed")


def _bg_log_discovery(items_snapshot: list[dict[str, Any]]) -> None:
    if not database_url_configured() or not _token_logging_enabled():
        return
    try:
        rows = rows_from_discovery_items(items_snapshot)
        if rows:
            upsert_dex_token_rows(rows)
    except Exception:  # noqa: BLE001
        _LOG.exception("dex_tokens: upsert after /feed/with-discovery failed")


def _bg_dispatch_pipeline(snapshot: list[dict[str, Any]]) -> None:
    try:
        run_alert_dispatch(snapshot)
    except Exception:  # noqa: BLE001
        _LOG.exception("pipeline telegram/discord dispatch failed")


class AlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_address: str
    chain_id: str
    symbol: str | None = None
    pair_address: str | None = None

    alert_score: float | None = None
    scoring_rules_version: str | None = None
    feature_snapshot: dict[str, Any] | list[Any] | None = None

    liquidity_usd: float | None = None
    volume_1h_usd: float | None = None
    volume_24h_usd: float | None = None
    price_change_1h: float | None = None
    price_change_24h: float | None = None
    buys_1h: int | None = None
    sells_1h: int | None = None
    market_cap_usd: float | None = None

    x_mentions_30m: int | None = None
    influencer_mentions: int | None = None

    mint_disabled: bool | None = None
    freeze_disabled: bool | None = None
    top_holder_percent: float | None = None
    rug_risk_score: float | None = None

    price_at_alert: float | None = None
    price_after_15m: float | None = None
    price_after_1h: float | None = None
    price_after_6h: float | None = None
    price_after_24h: float | None = None

    outcome_label: str | None = None
    reward_score: float | None = None

    rugged: bool = False

    telegram_message_id: str | None = None
    telegram_chat_id: str | None = None

    channel: str = "telegram"

PAIR_FETCH_CONCURRENCY = max(2, min(24, int(os.getenv("CORTISOL_PAIR_FETCH_CONCURRENCY", "6"))))
REQUEST_TIMEOUT = 45.0


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    broadcast_task: asyncio.Task[None] | None = None
    if OUTBOUND_WATCHLIST_WEBHOOK_URL and BROADCAST_WATCHLIST_SECONDS > 0:
        from broadcast.watchlist_webhook_loop import periodic_watchlist_webhook_loop

        broadcast_task = asyncio.create_task(
            periodic_watchlist_webhook_loop(),
            name="watchlist_webhook_broadcast",
        )
        _LOG.info("Started watchlist webhook broadcast loop")
    try:
        yield
    finally:
        if broadcast_task is not None:
            broadcast_task.cancel()
            try:
                await broadcast_task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="Cortisol",
    description=(
        "Market (Dex HTTP) → scoring → safety (RugCheck Solana stub path) "
        "→ Postgres logging → Telegram/Discord alerts → Jupiter preview links."
    ),
    version="0.5.0",
    lifespan=_lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)


async def load_merged_profiles() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        return await fetch_merged_token_profiles(client)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "cortisol",
        "status": "ok",
        "docs": "/docs",
        "endpoints": "/feed/with-discovery,/api/tokens,/api/alerts,/api/feed/with-discovery,/token-profiles/latest",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    db_status, db_detail = await asyncio.to_thread(db_health_sync)
    return {
        "status": "healthy",
        "database": {
            "status": db_status,
            "detail": db_detail,
        },
    }


@app.post("/api/alerts")
@app.post("/alerts")
async def create_alert(body: AlertCreate) -> dict[str, Any]:
    if not database_url_configured():
        raise HTTPException(status_code=503, detail=database_missing_detail())
    row = body.model_dump(exclude_unset=True)
    try:
        new_id = await asyncio.to_thread(insert_alert_row, row)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Failed to persist alert (did you apply backend/db/schema.sql?): {exc}",
        ) from exc
    return {"id": new_id}


@app.get("/api/alerts")
@app.get("/alerts")
async def list_alerts(
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="How many alerts to return (most recent first).",
    ),
) -> dict[str, Any]:
    if not database_url_configured():
        raise HTTPException(status_code=503, detail=database_missing_detail())
    try:
        rows = await asyncio.to_thread(list_alerts_recent, limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read alerts: {exc}",
        ) from exc
    return {"count": len(rows), "items": jsonable_encoder(rows)}


@app.get("/api/tokens")
@app.get("/tokens")
async def list_logged_tokens(
    limit: int = Query(
        default=100,
        ge=1,
        le=3000,
        description="Most recently seen tokens (by last_seen_at).",
    ),
) -> dict[str, Any]:
    if not database_url_configured():
        raise HTTPException(status_code=503, detail=database_missing_detail())
    try:
        rows = await asyncio.to_thread(list_dex_tokens_recent, limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read dex_tokens (apply backend/db/schema.sql?): {exc}",
        ) from exc
    return {"count": len(rows), "items": jsonable_encoder(rows)}


@app.get("/token-profiles/latest")
async def get_latest_token_profiles(
    background_tasks: BackgroundTasks,
    chain_id: str | None = Query(
        default=None,
        description="Filter results by chain (e.g. 'solana', 'ethereum').",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=220,
        description="Maximum profiles to return.",
    ),
) -> dict[str, Any]:
    """Merged Dex lists (profiles latest + recent updates + boosts + CTO + ads), deduped."""
    try:
        profiles, meta = await load_merged_profiles()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Dexscreener error: {exc.response.text}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach Dexscreener: {exc}") from exc

    if chain_id:
        chain_id_lc = chain_id.lower()
        profiles = [p for p in profiles if str(p.get("chainId") or "").lower() == chain_id_lc]

    if limit is not None:
        profiles = profiles[:limit]

    background_tasks.add_task(_bg_log_profiles, list(profiles))

    return {"count": len(profiles), "profiles": profiles, "feed_meta": meta}


@app.get("/feed/with-discovery")
@app.get("/api/feed/with-discovery")
async def feed_with_discovery(
    background_tasks: BackgroundTasks,
    chain_id: str | None = Query(
        default=None,
        description="Filter feed items by chain (e.g. 'solana', 'ethereum').",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=140,
        description="Maximum profiles to enrich (each triggers one pairs lookup).",
    ),
    mvp_pass_only: bool | None = Query(
        default=None,
        description=(
            "If true, return only tokens where all MVP market gates pass (liq/vol h1/buy-pressure/pair). "
            "If omitted, uses env CORTISOL_FEED_MATH_PASS_ONLY (default on)."
        ),
    ),
) -> dict[str, Any]:
    """Profiles enriched with Dex pairs → Cortisol MVP pipeline + optional alerts."""
    sem = asyncio.Semaphore(PAIR_FETCH_CONCURRENCY)
    safety_sem = asyncio.Semaphore(SAFETY_FETCH_CONCURRENCY)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        profiles, feed_meta = await fetch_merged_token_profiles(client)

        if not profiles:
            return {
                "count": 0,
                "bad_count": 0,
                "items": [],
                "feed_meta": feed_meta,
            }

        if chain_id:
            cid = chain_id.lower()
            profiles = [p for p in profiles if str(p.get("chainId") or "").lower() == cid]

        if limit is not None:
            profiles = profiles[:limit]

        async def one(profile: dict[str, Any]) -> dict[str, Any]:
            cid = str(profile.get("chainId") or "")
            addr = str(profile.get("tokenAddress") or "")
            async with sem:
                pairs_raw, ferr = await fetch_token_pairs(client, cid, addr)
                err = ferr
                pair_json = pick_primary_pair(pairs_raw, addr)

            metrics = compute_pair_metrics(pair_json)
            async with safety_sem:
                safety = await fetch_safety_bundle(client, chain_id=cid, token_address=addr)

            sym_hint = profile.get("symbol") or profile.get("ticker")
            sym_hint = str(sym_hint) if isinstance(sym_hint, str) else None

            slim_pair = None
            chart_fb = profile.get("url")
            if pair_json:
                chart_fb = pair_json.get("url") or chart_fb
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

            pipe = assemble_pipeline(
                profile=profile,
                metrics=metrics,
                safety=safety,
                chart_url_fallback=chart_fb,
                symbol_hint=sym_hint,
            )
            discovery = discovery_from_pipeline(pipe)

            return {
                "profile": profile,
                "pair": slim_pair,
                "pairs_found": len(pairs_raw),
                "pair_fetch_error": err,
                "discovery": discovery,
                "pipeline": pipe,
            }

        items = await asyncio.gather(*(one(p) for p in profiles))

    feed_meta_out = dict(feed_meta)
    apply_mvp_only = FEED_MATH_PASS_ONLY if mvp_pass_only is None else mvp_pass_only
    before_filter = len(items)
    visible = items
    if apply_mvp_only:
        visible = [
            it
            for it in items
            if isinstance(it.get("pipeline"), dict)
            and it["pipeline"].get("market_all_pass") is True
        ]
        feed_meta_out["mvp_math_pass_only"] = True
        feed_meta_out["items_before_mvp_filter"] = before_filter
        feed_meta_out["items_after_mvp_filter"] = len(visible)
    else:
        feed_meta_out["mvp_math_pass_only"] = False

    bad_items = sum(1 for it in visible if it["discovery"]["overall_bad"])
    items_copy = list(items)
    background_tasks.add_task(_bg_dispatch_pipeline, items_copy)
    background_tasks.add_task(_bg_log_discovery, items_copy)

    return {
        "count": len(visible),
        "bad_count": bad_items,
        "items": visible,
        "feed_meta": feed_meta_out,
    }


@app.get("/token-profiles/latest/{token_address}")
async def get_token_profile_by_address(token_address: str) -> dict[str, Any]:
    """Single profile from merged Dex lists matching token address."""
    profiles, _meta = await load_merged_profiles()
    target = token_address.lower()
    for profile in profiles:
        if str(profile.get("tokenAddress") or "").lower() == target:
            return profile
    raise HTTPException(
        status_code=404,
        detail=f"Token address '{token_address}' not found in merged profile lists.",
    )
