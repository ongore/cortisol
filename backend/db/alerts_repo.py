"""Read/write helpers for ``alerts`` rows."""

from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Json

from db.connection import db_connection


_INSERT_SQL = """
INSERT INTO alerts (
  token_address, chain_id, symbol, pair_address,
  alert_score, scoring_rules_version, feature_snapshot,
  liquidity_usd, volume_1h_usd, volume_24h_usd,
  price_change_1h, price_change_24h, buys_1h, sells_1h, market_cap_usd,
  x_mentions_30m, influencer_mentions,
  mint_disabled, freeze_disabled, top_holder_percent, rug_risk_score,
  price_at_alert, price_after_15m, price_after_1h, price_after_6h, price_after_24h,
  outcome_label, reward_score,
  rugged,
  telegram_message_id, telegram_chat_id,
  channel
) VALUES (
  %(token_address)s, %(chain_id)s, %(symbol)s, %(pair_address)s,
  %(alert_score)s, %(scoring_rules_version)s, %(feature_snapshot)s,
  %(liquidity_usd)s, %(volume_1h_usd)s, %(volume_24h_usd)s,
  %(price_change_1h)s, %(price_change_24h)s, %(buys_1h)s, %(sells_1h)s, %(market_cap_usd)s,
  %(x_mentions_30m)s, %(influencer_mentions)s,
  %(mint_disabled)s, %(freeze_disabled)s, %(top_holder_percent)s, %(rug_risk_score)s,
  %(price_at_alert)s, %(price_after_15m)s, %(price_after_1h)s, %(price_after_6h)s, %(price_after_24h)s,
  %(outcome_label)s, %(reward_score)s,
  %(rugged)s,
  %(telegram_message_id)s, %(telegram_chat_id)s,
  %(channel)s
)
RETURNING id;
"""


_SELECT_RECENT_SQL = """
SELECT
  id, token_address, chain_id, symbol, pair_address,
  alert_score, channel, rugged, created_at
FROM alerts
ORDER BY created_at DESC
LIMIT %(limit)s;
"""


def insert_alert_row(row: dict[str, Any]) -> int:
    """Insert one alert row. ``row`` must include token_address + chain_id; rest optional."""

    blob = dict(row)

    snapshot = blob.get("feature_snapshot")
    if snapshot is None:
        blob["feature_snapshot"] = None
    elif isinstance(snapshot, (dict, list)):
        blob["feature_snapshot"] = Json(snapshot)
    elif isinstance(snapshot, str):
        blob["feature_snapshot"] = Json(json.loads(snapshot))
    else:
        blob["feature_snapshot"] = Json(snapshot)

    keys = (
        "token_address",
        "chain_id",
        "symbol",
        "pair_address",
        "alert_score",
        "scoring_rules_version",
        "liquidity_usd",
        "volume_1h_usd",
        "volume_24h_usd",
        "price_change_1h",
        "price_change_24h",
        "buys_1h",
        "sells_1h",
        "market_cap_usd",
        "x_mentions_30m",
        "influencer_mentions",
        "mint_disabled",
        "freeze_disabled",
        "top_holder_percent",
        "rug_risk_score",
        "price_at_alert",
        "price_after_15m",
        "price_after_1h",
        "price_after_6h",
        "price_after_24h",
        "outcome_label",
        "reward_score",
        "rugged",
        "telegram_message_id",
        "telegram_chat_id",
        "channel",
    )
    defaults: dict[str, Any] = {k: None for k in keys}
    defaults["rugged"] = False
    defaults["channel"] = "telegram"
    merged = defaults | blob

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_INSERT_SQL, merged)
            new_id = cur.fetchone()[0]
        conn.commit()
    return int(new_id)


def list_alerts_recent(limit: int) -> list[dict[str, Any]]:
    limit = max(1, min(200, int(limit)))
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_RECENT_SQL, {"limit": limit})
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return rows
