import type { DiscoveryFeedResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export async function fetchDiscoveryFeed(params?: {
  chain_id?: string;
  limit?: number;
}): Promise<DiscoveryFeedResponse> {
  const search = new URLSearchParams();
  if (params?.chain_id) search.set("chain_id", params.chain_id);
  if (params?.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  const url = `${API_BASE}/feed/with-discovery${qs ? `?${qs}` : ""}`;

  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}
