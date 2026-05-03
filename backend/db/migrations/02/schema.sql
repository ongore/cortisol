-- Cortisol alerts store. Run once in Supabase: SQL Editor → paste → Run.

BEGIN;

CREATE TABLE IF NOT EXISTS alerts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    token_address TEXT NOT NULL,
    chain_id TEXT NOT NULL,
    symbol TEXT,
    pair_address TEXT,

    alert_score NUMERIC,
    scoring_rules_version TEXT,
    feature_snapshot JSONB,

    liquidity_usd NUMERIC,
    volume_1h_usd NUMERIC,
    volume_24h_usd NUMERIC,
    price_change_1h NUMERIC,
    price_change_24h NUMERIC,
    buys_1h INTEGER,
    sells_1h INTEGER,
    market_cap_usd NUMERIC,

    x_mentions_30m INTEGER,
    influencer_mentions INTEGER,

    mint_disabled BOOLEAN,
    freeze_disabled BOOLEAN,
    top_holder_percent NUMERIC,
    rug_risk_score NUMERIC,

    price_at_alert NUMERIC,
    price_after_15m NUMERIC,
    price_after_1h NUMERIC,
    price_after_6h NUMERIC,
    price_after_24h NUMERIC,

    outcome_label TEXT,
    reward_score NUMERIC,

    rugged BOOLEAN NOT NULL DEFAULT FALSE,
    telegram_message_id TEXT,
    telegram_chat_id TEXT,

    channel TEXT NOT NULL DEFAULT 'telegram',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    outcomes_updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_alerts_token_chain ON alerts (chain_id, token_address);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts (created_at DESC);

CREATE TABLE IF NOT EXISTS alert_feedback (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES alerts (id) ON DELETE CASCADE,
    feedback TEXT NOT NULL,
    telegram_user_id TEXT,
    telegram_username TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_feedback_alert ON alert_feedback (alert_id);

-- Tokens observed from Dex merged profiles / discovery feed (upsert per poll).
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

-- Alerts actually emitted via Telegram / Discord webhook (audit + cooldown).
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
