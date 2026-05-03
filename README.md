# cortisol

A surveillance terminal for the chain. FastAPI merges [Dexscreener](https://docs.dexscreener.com/) token lists + pair metrics; the **Cortisol pipeline** applies MVP thresholds, Solana RugCheck summaries, Postgres logging, Telegram/Discord fan-out (when configured), and Jupiter preview links in the SPA.

## Cortisol infra (layers)

Target stack aligns with Dex → gates → safety → alerts → swap execution:

| Layer | Implemented now | Env / hooks |
|-------|-----------------|-------------|
| Market | Dex HTTPS merges (`feed_sources`), pair cache (`dex_pairs`), primary pair heuristic (`discovery.pick_primary_pair`) | `CORTISOL_*` Dex pacing knobs |
| Scoring | `pipeline/build.py` MVP gates (**default $25k liq**, **$50k vol h1**, **buys>sells**) + composite signal | `CORTISOL_MVP_*` |
| Safety | Solana **`GET /v1/tokens/{mint}/report/summary`** via RugCheck; EVM stubs for GoPlus (v5) | `CORTISOL_SAFETY_*`, `CORTISOL_RUGCHECK_*` |
| Social | Typed stub only (defer X pricing to v6) | — |
| Alerts | Telegram `sendMessage` + Discord webhook after each **`/feed/with-discovery`** BackgroundTask | `TELEGRAM_*`, `DISCORD_*`, cooldown `signal_dispatches` |
| Execution | Jupiter *UI* deeplink preview for Solana; Phantom signing + quote API slated v3/v4 | `integrations/buy_links.py` |

Roadmap placeholders still in JSON under each item’s **`pipeline.integrations`** (Helius RPC, Dex WS, Birdeye, GoPlus).

## Stack

- **Backend**: Python 3.11+, FastAPI, httpx (`backend/`)
- **Frontend**: Vite + React 18 + TypeScript + Tailwind CSS v4 (`frontend/`)

## Layout

```
cortisol/
├── backend/
│   ├── main.py           # FastAPI app
│   ├── cortisol_config.py # MVP thresholds + integrations
│   ├── feed_sources.py   # merges Dex buckets + TTL cache + profile dedupe
│   ├── dex_pairs.py       # token-pairs cache + 429 backoff
│   ├── discovery.py      # chooses richest pair for scoring
│   ├── pipeline/         # MVP gates + roadmap payload (→ SPA `pipeline`)
│   ├── safety/           # RugCheck Solana summaries + EVM stubs
│   ├── integrations/     # Telegram, Discord, Jupiter preview links
│   ├── alerts/           # Dispatch + cooldown orchestration
│   ├── domain/           # pair metric extraction (`pair_metrics`)
│   ├── requirements.txt
│   ├── db/
│   │   └── schema.sql    # Supabase SQL: alerts, feedback, dex_tokens, signal_dispatches
│   └── .env.example      # copy to `.env` for DATABASE_URL etc.
└── frontend/             # Vite + React + Tailwind UI
```

## Run both

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Server: `http://127.0.0.1:8000` · Docs: `http://127.0.0.1:8000/docs`.

Restart `uvicorn` after pulling changes (`GET /feed/with-discovery` can **404** if an old process is still bound to the wrong cwd).

Secrets (e.g. Supabase): create `backend/.env` matching `backend/.env.example`. That file is gitignored.

**Postgres (Supabase):** In the Supabase dashboard open **SQL** → **New query**, paste `backend/db/schema.sql`, run it once. Then copy the Postgres URI from **Project Settings → Database → Connection string** into **`DATABASE_URL`** in `backend/.env` (or **`SUPABASE_DATABASE_URL`** if **`DATABASE_URL`** is empty). Direct (`db.<project-ref>.supabase.co`) and Session pooler (`*.pooler.supabase.com`) both work; this backend appends **`sslmode=require`** when omitted. Restart uvicorn.

- **`GET /health`** includes **`database.status`**: **`not_configured`**, **`ok`**, or **`error`** (+ optional **`detail`**).
- **`POST /alerts`** (or **`/api/alerts`**) persists a row; **`GET /alerts?limit=50`** lists recent alerts. Through the SPA dev proxy, use **`POST /api/alerts`** and **`GET /api/alerts`**.
- Responses from **`GET /feed/with-discovery`** may **emit Telegram / Discord alerts** after the response returns (BackgroundTasks) whenever **`eligible_for_*`** gates pass **and** `TELEGRAM_BOT_TOKEN` / `DISCORD_ALERT_WEBHOOK_URL` are configured. Cooldown tracked in Postgres **`signal_dispatches`** when `DATABASE_URL` is set.

- Responses from **`GET /token-profiles/latest`** and **`GET /feed/with-discovery`** **upsert** each token into **`dex_tokens`** (chain, address, symbol, optional primary pair address, **`seen_count`**, first/last seen) when **`DATABASE_URL`** is set. Disable with **`CORTISOL_LOG_TOKENS_TO_DB=0`**. Inspect with **`GET /tokens?limit=100`** (SPA: **`GET /api/tokens`**).

Example (after migrations + `DATABASE_URL`):

```bash
curl -s -X POST http://127.0.0.1:8000/alerts \
  -H 'Content-Type: application/json' \
  -d '{"token_address":"So11111111111111111111111111111111111111112","chain_id":"solana","alert_score":0.42}'
curl -s 'http://127.0.0.1:8000/alerts?limit=5'
curl -s 'http://127.0.0.1:8000/tokens?limit=20'
```

If you migrated before **`dex_tokens`** or **`signal_dispatches`** existed, paste those `CREATE TABLE` blocks from **`backend/db/schema.sql`** into the Supabase SQL editor and run them.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

UI: **`http://localhost:5173`**. Requests go to **`/api/…`** → Vite proxies to **`http://127.0.0.1:8000/…`** (see `vite.config.ts`). Keep **FastAPI running on port 8000** while developing.

Also works with **`npm run preview`** (port **4173**): preview uses the **same `/api` proxy**, so uvicorn still must be reachable on **`127.0.0.1:8000`**.

If **`VITE_API_BASE`** is set empty in `.env`, it is ignored and **`/api`** is used — an empty base would skip the proxy and break the feed.

Production static hosting has **no proxy** unless you configure nginx (or rebuild with **`VITE_API_BASE=https://your-api`**).

The UI loads **`GET /api/feed/with-discovery`** (proxied): the backend merges several Dex bucket lists (**recent updates, boosts latest/top, community takeovers, ads, profiles latest**) into one deduped set (~100+ tokens vs ~30 per list), pulls **`token-pairs/v1/{chain}/{token}`**, applies **MVP gates + RugCheck (Solana)**, returns **`pipeline`** + **`discovery`**, and may fan out Telegram/Discord when env keys are present.

Merged profiles are cached for **`CORTISOL_PROFILE_CACHE_SECONDS`** (default `55`) so periodic UI refresh does not issue repeated Dex merges each tick against free-tier rate limits. Tune **`CORTISOL_DEX_LIST_PAUSE_SECONDS`** (default **`1.1`**) plus **`CORTISOL_DEX_FALLBACK_COOLDOWN_SECONDS`** (default **`2.0`**) if you hit HTTP **429** on the *bucket* endpoints.

**Token-pairs fan-out:** Each enriched token calls Dex **`/token-pairs/v1/{chain}/{token}`**. Requests are capped at **`CORTISOL_PAIR_FETCH_CONCURRENCY`** parallel in-flight calls (default **`6`**), each response is cached (**`CORTISOL_PAIR_CACHE_SECONDS`**, default **`55`**), with short **429** retries.

### Backend “never connects” to the SPA

Connections are initiated by the **browser** (`fetch`), not by FastAPI dialing the UI.

1. Run **both**: `uvicorn main:app --reload` **from `backend/`** **and** `npm run dev` **from `frontend/`**.
2. Open the app at **`http://localhost:5173`** or **`http://127.0.0.1:5173`** (stay consistent with whichever you use elsewhere).
3. With default settings, UI calls **`/api/health`** → Vite proxies to **`http://127.0.0.1:8000/health`**. The sidebar **FastAPI** row turns green when that succeeds.
4. If you build with **`VITE_API_BASE=http://127.0.0.1:8000`**, the UI talks to FastAPI **directly**; CORS must allow your dev origin (already includes ports **5173** and **4173**).
5. **`npm run preview`** only proxies `/api` if you added the same **`preview.proxy`** block (already in **`vite.config.ts`**); **static `dist/` on random hosts does not**.
6. Telegram + Discord hooks run **inside FastAPI BackgroundTasks** (see **`alerts/`**). Configure **`TELEGRAM_BOT_TOKEN`**, **`TELEGRAM_ALERT_CHAT_IDS`**, and/or **`DISCORD_ALERT_WEBHOOK_URL`**; disable globally with **`CORTISOL_ALERT_DISPATCH_ENABLED=0`**. Slash commands (`/boosts`) still land in your future Telegram worker (beyond this polling stack).

## Endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/` | Service metadata |
| GET | `/health` | Health check (**`database`** sub-object when Postgres is configured) |
| POST | `/alerts`, `/api/alerts` | Create alert row (**requires** `DATABASE_URL` + schema) |
| GET | `/alerts`, `/api/alerts` | Recent alerts (**`limit`**, default **50**) |
| GET | `/tokens`, `/api/tokens` | Recently seen Dex tokens from **`dex_tokens`** (**`limit`**, default **100**) |
| GET | `/feed/with-discovery` | Profiles + primary pair + discovery flags |
| GET | `/api/feed/with-discovery` | Same (for Vite `/api` proxy) |
| GET | `/feed/with-discovery?chain_id=solana&limit=20` | Filter / cap enrichment |
| GET | `/token-profiles/latest` | Deduped merge of multiple Dex bucket lists (~30 each → dozens–100+ unique) |
| GET | `/token-profiles/latest?chain_id=solana` | Filter by chain |
| GET | `/token-profiles/latest?limit=10` | Cap profiles |
| GET | `/token-profiles/latest/{token_address}` | Look up profile by address |

## Examples

Run the backend (`cd backend` + `uvicorn` above), then:

```bash
curl 'http://127.0.0.1:8000/feed/with-discovery?limit=5'
curl http://127.0.0.1:8000/token-profiles/latest?chain_id=solana&limit=5
curl http://127.0.0.1:8000/token-profiles/latest/0x5C9e5E02c6F1f9b386fCfc6EEb7da4f33E091c7A
```
