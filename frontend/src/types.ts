export interface TokenLink {
  type?: string;
  label?: string;
  url: string;
}

export interface TokenProfile {
  url: string;
  chainId: string;
  tokenAddress: string;
  icon?: string;
  header?: string | null;
  openGraph?: string;
  description?: string | null;
  links?: TokenLink[];
  cto?: boolean;
  updatedAt?: string;
}

export interface FeedMeta {
  source_endpoints: number;
  unique_tokens: number;
  sources_failed?: number;
  upstream_errors?: { source: string; detail: string }[] | null;
  fallback?: string | null;
  /** Backend: only tokens passing all MVP market gates (liquidity, vol h1, buy pressure, pair). */
  mvp_math_pass_only?: boolean;
  items_before_mvp_filter?: number;
  items_after_mvp_filter?: number;
}

export interface ProfilesResponse {
  count: number;
  profiles: TokenProfile[];
  feed_meta?: FeedMeta;
}

export interface DiscoveryFlag {
  severity: "bad" | "warn";
  key: string;
  label: string;
}

export interface DiscoveryPositive {
  key: string;
  label: string;
}

export interface DiscoveryMetrics {
  liquidity_usd: number | null;
  volume_h1: number | null;
  volume_h24: number | null;
  txns_h1_total: number | null;
  buys_h1: number | null;
  sells_h1: number | null;
  buy_sell_ratio_h1: number | null;
  pair_age_hours: number | null;
  pair_age_days: number | null;
  fdv: number | null;
  market_cap: number | null;
  price_change_m5: number | null;
  price_change_h1: number | null;
  dex_id?: string | null;
  pair_address?: string | null;
  pair_url?: string | null;
}

export interface DiscoveryResult {
  overall_bad: boolean;
  bad_count: number;
  warn_count: number;
  metrics: DiscoveryMetrics;
  flags: DiscoveryFlag[];
  positives: DiscoveryPositive[];
  summary: "BAD" | "WARN" | "OK";
}

/** Backend Cortisol MVP pipeline (market → safety stubs → integrations). */
export interface CortisolPipeline {
  version?: string;
  signal_score?: number;
  risk_label?: string;
  market_all_pass?: boolean;
  eligible_for_trade_alert?: boolean;
  eligible_for_telegram?: boolean;
  mvp_gates_market?: Record<string, boolean>;
  safety_tier?: string;
  actions?: {
    chart_url?: string | null;
  };
  integrations?: {
    telegram?: { configured?: boolean };
    discord?: { configured?: boolean };
    jupiter?: {
      ready?: boolean;
      swap_preview_url_solana?: string | null;
    };
    phantom?: { browse_template?: string | null };
    helius?: { rpc_configured?: boolean };
  };
}

export interface SlimPair {
  chainId?: string;
  dexId?: string;
  pairAddress?: string;
  url?: string;
  priceUsd?: string;
  liquidity?: Record<string, unknown>;
  volume?: Record<string, unknown>;
  txns?: Record<string, unknown>;
  priceChange?: Record<string, unknown>;
  fdv?: number;
  marketCap?: number;
  pairCreatedAt?: number;
  baseToken?: Record<string, unknown>;
  quoteToken?: Record<string, unknown>;
}

export interface FeedItem {
  profile: TokenProfile;
  pair: SlimPair | null;
  pairs_found: number;
  pair_fetch_error: string | null;
  discovery: DiscoveryResult;
  pipeline?: CortisolPipeline | null;
}

export interface DiscoveryFeedResponse {
  count: number;
  bad_count: number;
  items: FeedItem[];
  feed_meta?: FeedMeta;
}
