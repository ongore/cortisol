-- Incremental migration: run in Supabase SQL Editor if you already created
-- `alerts` and `alert_feedback` but are missing token logging / dispatch audit tables.

BEGIN;

CREATE TABLE IF NOT EXISTS dex_tokens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chain_id TEXT NOT NULL,
    token_address TEXT NOT NULL,
    symbol TEXT,
    pair_address TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    seen_count BIGINT NOT NULL DEFAULT 1,

    UNIQUE (chain_id, token_address)
);

CREATE INDEX IF NOT EXISTS idx_dex_tokens_last_seen ON dex_tokens (last_seen_at DESC);

CREATE TABLE IF NOT EXISTS signal_dispatches (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chain_id TEXT NOT NULL,
    token_address TEXT NOT NULL,
    rules_version TEXT,
    signal_score NUMERIC,
    telegram_ok BOOLEAN NOT NULL DEFAULT FALSE,
    discord_ok BOOLEAN NOT NULL DEFAULT FALSE,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_dispatch_token_time ON signal_dispatches (
    chain_id,
    token_address,
    created_at DESC
);

COMMIT;
