"""Central env-driven thresholds & integration flags."""

from __future__ import annotations

import os


def env_float(name: str, default: str) -> float:
    raw = os.getenv(name, default).strip()
    return float(raw)


def env_int(name: str, default: str) -> int:
    return int(env_float(name, default))


def env_truthy(name: str, *, default_true: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default_true
    v = raw.strip().lower()
    if v in ("", "0", "false", "no", "off"):
        return False
    return True


RULES_VERSION = os.getenv(
    "CORTISOL_SCORING_RULES_VERSION",
    "cortisol-mvp-2026-02-market+safety-alert",
)


# ── MVP gates (Dex path) ───────────────────────────────────────────────
MIN_LIQ_USD = env_float("CORTISOL_MVP_MIN_LIQUIDITY_USD", "25000")
MIN_VOL_H1_USD = env_float("CORTISOL_MVP_MIN_VOLUME_H1_USD", "50000")
REQUIRE_BUYS_GT_SELLS = env_truthy("CORTISOL_MVP_REQUIRE_BUYS_GT_SELLS", default_true=True)

# ── Safety (RugCheck Solana — v5 precursor) ─────────────────────────────
RUGCHECK_BASE = os.getenv("CORTISOL_RUGCHECK_API_BASE", "https://api.rugcheck.xyz").rstrip("/")
SAFETY_STRICT = env_truthy("CORTISOL_SAFETY_STRICT", default_true=False)
SAFETY_FAIL_OPEN = env_truthy("CORTISOL_SAFETY_FAIL_OPEN", default_true=True)
RUCRISK_CRITICAL_SCORE_MIN = env_int("CORTISOL_RUGCHECK_CRITICAL_SCORE", "4999")

# ── Alert fan-out ──────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ALERT_CHAT_IDS = [
    x.strip()
    for x in os.getenv("TELEGRAM_ALERT_CHAT_IDS", "").split(",")
    if x.strip()
]
DISCORD_ALERT_WEBHOOK_URL = os.getenv("DISCORD_ALERT_WEBHOOK_URL", "").strip()

ALERT_COOLDOWN_SECONDS = env_int("CORTISOL_ALERT_COOLDOWN_SECONDS", "900")
ALERT_DISPATCH_ENABLED = env_truthy("CORTISOL_ALERT_DISPATCH_ENABLED", default_true=True)

# ── Helius / Phantom / Jupiter stubs (wired in frontend + later swap API) ─
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "").strip()
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "").strip()

SAFETY_FETCH_CONCURRENCY = max(
    1,
    min(12, env_int("CORTISOL_SAFETY_FETCH_CONCURRENCY", "4")),
)

# ── Outbound webhook: periodic Dex snapshots for rows in dex_tokens ─────
OUTBOUND_WATCHLIST_WEBHOOK_URL = os.getenv("OUTBOUND_WATCHLIST_WEBHOOK_URL", "").strip()
OUTBOUND_WATCHLIST_WEBHOOK_SECRET = os.getenv("OUTBOUND_WATCHLIST_WEBHOOK_SECRET", "").strip()
# Target interval between ticks. A tick SKIPs if the previous refresh is still running.
BROADCAST_WATCHLIST_SECONDS = env_float("CORTISOL_BROADCAST_WATCHLIST_SECONDS", "30")
BROADCAST_WATCHLIST_TOKEN_LIMIT = max(
    1,
    min(3000, env_int("CORTISOL_BROADCAST_WATCHLIST_TOKEN_LIMIT", "250")),
)
BROADCAST_PAIR_CONCURRENCY = max(2, min(32, env_int("CORTISOL_BROADCAST_PAIR_CONCURRENCY", "8")))

# Feed: hide illiquid / no-volume / bad buy-pressure tokens (MVP gates all pass).
FEED_MATH_PASS_ONLY = env_truthy("CORTISOL_FEED_MATH_PASS_ONLY", default_true=True)
