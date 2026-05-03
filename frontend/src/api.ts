import type { DiscoveryFeedResponse } from "./types";

const apiBaseEnv =
  typeof import.meta.env.VITE_API_BASE === "string"
    ? import.meta.env.VITE_API_BASE.trim()
    : "";
/** Empty string in .env wrongly bypasses the Vite `/api` proxy. */
export const RESOLVED_API_BASE =
  apiBaseEnv.length > 0 ? apiBaseEnv.replace(/\/$/, "") : "/api";

export const API_TRANSPORT: "vite-proxy" | "direct-url" =
  apiBaseEnv.length > 0 ? "direct-url" : "vite-proxy";

function isLikelyAbortError(cause: unknown): boolean {
  if (typeof cause !== "object" || cause === null) return false;
  const name =
    "name" in cause && typeof (cause as { name: unknown }).name === "string"
      ? (cause as { name: string }).name
      : "";
  return name === "AbortError";
}

function wrapFetchError(operation: string, url: string, cause: unknown): Error {
  const base = `${operation} (${url})`;
  if (isLikelyAbortError(cause)) {
    return new Error(`${base}: timeout — FastAPI likely not reachable.`);
  }
  if (
    cause instanceof TypeError &&
    typeof cause.message === "string" &&
    /fetch|failed|network|Load failed/i.test(cause.message)
  ) {
    return new Error(
      `${base}: ${cause.message} — Start uvicorn (\`cd backend && uvicorn main:app --reload\`). Dev uses RESOLVED_API_BASE=${RESOLVED_API_BASE} (vite proxy expects FastAPI at 127.0.0.1:8000).`,
    );
  }
  const msg = cause instanceof Error ? cause.message : String(cause);
  return new Error(`${base}: ${msg}`);
}

/** Quick probe — same path resolution as feed (proxy or VITE_API_BASE). */
export async function checkBackendHealth(
  timeoutMs = 4500,
): Promise<{ ok: boolean; latencyMs?: number; detail: string }> {
  const url = `${RESOLVED_API_BASE}/health`;
  const t0 =
    typeof performance !== "undefined" ? performance.now() : Date.now();
  const ctrl = new AbortController();
  const timer = globalThis.setTimeout(() => ctrl.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      headers: { Accept: "application/json" },
      signal: ctrl.signal,
      cache: "no-store",
    });
    globalThis.clearTimeout(timer);
    const t1 =
      typeof performance !== "undefined" ? performance.now() : Date.now();

    if (!res.ok) {
      return {
        ok: false,
        detail: `HTTP ${res.status}: ${await res.text().catch(() => res.statusText)}`,
      };
    }

    await res.json().catch(() => undefined);
    return {
      ok: true,
      latencyMs: Math.round(t1 - t0),
      detail: "healthy",
    };
  } catch (e) {
    globalThis.clearTimeout(timer);
    const err = wrapFetchError("GET /health", url, e);
    return { ok: false, detail: err.message };
  }
}

export async function fetchDiscoveryFeed(params?: {
  chain_id?: string;
  limit?: number;
  /** Omit to use backend env (default: math-pass only). Pass false for full merged list. */
  mvp_pass_only?: boolean;
}): Promise<DiscoveryFeedResponse> {
  const search = new URLSearchParams();
  if (params?.chain_id) search.set("chain_id", params.chain_id);
  if (params?.limit != null) search.set("limit", String(params.limit));
  if (params?.mvp_pass_only !== undefined) {
    search.set("mvp_pass_only", params.mvp_pass_only ? "true" : "false");
  }
  const qs = search.toString();
  const url = `${RESOLVED_API_BASE}/feed/with-discovery${qs ? `?${qs}` : ""}`;

  try {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`API ${res.status}: ${text || res.statusText}`);
    }
    return res.json();
  } catch (e) {
    if (
      e instanceof Error &&
      typeof e.message === "string" &&
      /^API\s\d+:/i.test(e.message)
    )
      throw e;
    throw wrapFetchError("GET /feed/with-discovery", url, e);
  }
}
