"""Persistence for Telegram / Discord emits (audit + cooldown)."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Json

from db.connection import db_connection



def recent_dispatch_count(chain_id: str, token_address: str, *, max_age_seconds: int) -> int:
    cid = chain_id.strip().lower()
    tok = token_address.strip().lower()
    mx = max(30, min(172_800, int(max_age_seconds)))
    sql = """
    SELECT COUNT(*) FROM signal_dispatches
    WHERE chain_id = %(c)s AND lower(token_address) = %(t)s
      AND created_at > NOW() - CAST(%(win_literal)s AS interval);
    """
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                {"c": cid, "t": tok, "win": mx, "win_literal": f"{mx} seconds"},
            )
            row = cur.fetchone()
        conn.commit()
    return int(row[0] if row else 0)


def log_dispatch(
    *,
    chain_id: str,
    token_address: str,
    rules_version: str | None,
    signal_score: float | None,
    telegram_ok: bool,
    discord_ok: bool,
    payload: dict[str, Any],
) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO signal_dispatches (
                  chain_id, token_address, rules_version, signal_score,
                  telegram_ok, discord_ok, payload
                ) VALUES (
                  %(chain_id)s, %(token_address)s, %(rules_version)s, %(signal_score)s,
                  %(telegram_ok)s, %(discord_ok)s, %(payload)s
                )
                """,
                {
                    "chain_id": chain_id.strip().lower(),
                    "token_address": token_address.strip().lower(),
                    "rules_version": rules_version,
                    "signal_score": signal_score,
                    "telegram_ok": telegram_ok,
                    "discord_ok": discord_ok,
                    "payload": Json(payload),
                },
            )
        conn.commit()
