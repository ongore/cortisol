# cortisol

A surveillance terminal for the chain. FastAPI backend that proxies the [Dexscreener token-profiles API](https://api.dexscreener.com/token-profiles/latest/v1) plus a React + Tailwind frontend that visualizes the feed.

## Stack

- **Backend**: Python 3.11+, FastAPI, httpx
- **Frontend**: Vite + React 18 + TypeScript + Tailwind CSS v4

## Layout

```
cortisol/
├── main.py              # FastAPI app
├── discovery.py         # Pair scoring vs discovery rubric
├── requirements.txt
└── frontend/            # Vite + React + Tailwind UI
```

## Run both

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Server: `http://127.0.0.1:8000` &middot; Docs: `http://127.0.0.1:8000/docs`.

After pulling changes, restart `uvicorn` so routes reload (`GET /feed/with-discovery` returns **404** if an old process is still running).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

UI: `http://localhost:5173`. Vite proxies `/api/*` &rarr; the FastAPI backend.

The UI loads **`GET /feed/with-discovery`**, which merges token profiles with **`GET .../token-pairs/v1/{chain}/{token}`** and applies liquidity / volume / flow / age / FDV / momentum checks.

## Endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/` | Service metadata |
| GET | `/health` | Health check |
| GET | `/feed/with-discovery` | Profiles + primary pair + discovery flags (used by UI) |
| GET | `/feed/with-discovery?chain_id=solana&limit=20` | Filter / cap enrichment (each row = one pairs lookup) |
| GET | `/token-profiles/latest` | Profiles only (no pair calls) |
| GET | `/token-profiles/latest?chain_id=solana` | Filter by chain |
| GET | `/token-profiles/latest?limit=10` | Cap profiles |
| GET | `/token-profiles/latest/{token_address}` | Look up profile by address |

## Examples

```bash
curl 'http://127.0.0.1:8000/feed/with-discovery?limit=5'
curl http://127.0.0.1:8000/token-profiles/latest?chain_id=solana&limit=5
curl http://127.0.0.1:8000/token-profiles/latest/0x5C9e5E02c6F1f9b386fCfc6EEb7da4f33E091c7A
```
