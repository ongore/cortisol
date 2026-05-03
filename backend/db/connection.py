"""Postgres connectivity for health checks and repositories."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_DIR / ".env")

# Matches Supabase dashboard env names: DATABASE_URL ("Transaction pooler" / migrations)
# vs SUPABASE_DATABASE_URL (often same URI in snippets). Prefer DATABASE_URL first.
_DATABASE_URL_KEYS: tuple[str, ...] = ("DATABASE_URL", "SUPABASE_DATABASE_URL")


def _picked_database_url() -> str | None:
    """First non-empty Postgres URI from DATABASE_URL then SUPABASE_DATABASE_URL."""

    for key in _DATABASE_URL_KEYS:
        raw = os.getenv(key, "").strip()
        if raw:
            return raw
    return None


def database_url_configured() -> bool:
    return _picked_database_url() is not None


def database_missing_detail() -> str:
    opts = " or ".join(_DATABASE_URL_KEYS)
    return (
        f"Postgres URI not set — assign {opts} in backend/.env. "
        "Supabase Dashboard → Project Settings → Database → Connection string. "
        "For uvicorn backends use Direct "
        "(db.<project-ref>.supabase.co:5432/postgres) or Session pool "
        "(…pooler.supabase.com:6543/postgres). URL-encode special characters in passwords."
    )


def _effective_conninfo(url: str) -> str:
    """Supabase Postgres expects TLS; append sslmode when the URI omits it."""

    u = url.strip()
    low = u.lower()
    if "sslmode=" in low:
        return u
    if not low.startswith(("postgresql://", "postgres://")):
        return u
    try:
        host = (urlparse(u).hostname or "").lower().rstrip(".")
    except ValueError:
        return u

    wants_ssl = False
    if host.endswith(".supabase.co"):
        wants_ssl = True
    elif host.endswith(".pooler.supabase.com"):
        wants_ssl = True

    if wants_ssl:
        sep = "&" if "?" in u else "?"
        return f"{u}{sep}sslmode=require"
    return u


def _postgres_uri_requires_netloc_hostname(url: str) -> tuple[bool, str | None]:
    """
    Typical libpq URIs need a DNS host or IP. Broken strings like postgres://...@:5432/db
    parse with hostname None and produce useless errors (Errno 8 nodename …).
    """
    u = url.strip()
    if not u.lower().startswith(("postgres://", "postgresql://")):
        return False, None
    p = urlparse(u)
    if p.hostname:
        return False, None
    if not p.netloc:
        # e.g. postgresql:///dbname (local default socket — rare here)
        return False, None
    return True, (
        "DATABASE_URL or SUPABASE_DATABASE_URL looks malformed: no hostname "
        "(often postgres://...@:5432/...). Paste the Postgres URI from "
        "Supabase Dashboard → Database → Connection string (Direct "
        "`db.<project-ref>.supabase.co:5432/postgres`, or Session pool "
        "`*.pooler.supabase.com:6543/postgres`; URL-encode special characters "
        "in passwords)."
    )


@contextmanager
def db_connection(timeout_s: int = 8) -> Iterator[Any]:
    import psycopg

    url = _picked_database_url()
    if not url:
        raise RuntimeError(database_missing_detail())
    broken, hint = _postgres_uri_requires_netloc_hostname(url)
    if broken:
        raise RuntimeError(hint or "Postgres URI is missing hostname")
    with psycopg.connect(conninfo=_effective_conninfo(url), connect_timeout=timeout_s) as conn:
        yield conn


def db_health_sync() -> tuple[str, str | None]:
    """
    Returns (status, detail) where status ∈ not_configured, ok, error.
    """
    if not database_url_configured():
        return "not_configured", None
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        return "error", str(exc)[:400]
    return "ok", None
