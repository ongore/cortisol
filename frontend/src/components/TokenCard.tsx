import { useState } from "react";
import type { FeedItem, TokenLink } from "../types";

interface TokenCardProps {
  item: FeedItem;
  index: number;
}

const LINK_CODE: Record<string, string> = {
  twitter: "X",
  telegram: "TG",
  reddit: "RDT",
  tiktok: "TT",
  instagram: "IG",
  discord: "DC",
};

function linkCode(link: TokenLink): string {
  if (link.type && LINK_CODE[link.type.toLowerCase()]) {
    return LINK_CODE[link.type.toLowerCase()];
  }
  if (link.label) {
    return link.label.slice(0, 3).toUpperCase();
  }
  if (link.type) {
    return link.type.slice(0, 3).toUpperCase();
  }
  return "URL";
}

function shortAddress(addr: string): string {
  if (addr.length <= 12) return addr;
  return `${addr.slice(0, 6)}…${addr.slice(-6)}`;
}

function timeAgo(iso?: string): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.max(0, now - then);
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  return `${d}d`;
}

function fmtUsd(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}k`;
  return `$${n.toFixed(0)}`;
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

function fmtAgeHours(h: number | null | undefined): string {
  if (h == null || Number.isNaN(h)) return "—";
  if (h < 48) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

function fmtRatio(r: number | null | undefined): string {
  if (r === null) return "∞";
  if (r === undefined || Number.isNaN(r)) return "—";
  if (r > 99) return "99+";
  return r.toFixed(2);
}

function MetricCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-[var(--color-line)] px-2 py-1.5 bg-[var(--color-bg)]">
      <div className="font-mono text-[9px] tracking-[0.2em] uppercase text-[var(--color-ink-faint)] mb-0.5">
        {label}
      </div>
      <div className="font-mono text-[11px] tab-num tracking-tight text-[var(--color-ink)]">
        {value}
      </div>
    </div>
  );
}

export function TokenCard({ item, index }: TokenCardProps) {
  const { profile, discovery, pair_fetch_error } = item;
  const m = discovery.metrics;
  const [copied, setCopied] = useState(false);

  const href = item.pair?.url ?? profile.url;
  const banner = profile.header || profile.openGraph;

  const summary = discovery.summary;
  const summaryStyles =
    summary === "BAD"
      ? "bg-[var(--color-blood)] text-[var(--color-bg)]"
      : summary === "WARN"
        ? "border border-[var(--color-amber)] text-[var(--color-amber)]"
        : "border border-[var(--color-acid)] text-[var(--color-acid)]";

  const copy = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    navigator.clipboard.writeText(profile.tokenAddress).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    });
  };

  const badBorder = discovery.overall_bad
    ? "border-l-[3px] border-l-[var(--color-blood)]"
    : "";

  const positives = discovery.positives.slice(0, 6);
  const pipe = item.pipeline;
  const buyUrl = pipe?.integrations?.jupiter?.swap_preview_url_solana ?? null;

  return (
    <div
      className={
        "relative group reveal block hairline bg-[var(--color-bg-2)] hover:border-[var(--color-acid)] transition-colors duration-200 " +
        badBorder
      }
      style={{ animationDelay: `${Math.min(index * 40, 600)}ms` }}
    >
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="absolute inset-0 z-[10]"
        aria-label="Open Dex pair / chart"
      />
      <div className="relative z-[20] pointer-events-none flex flex-col">
      <div className="flex items-center justify-between border-b border-[var(--color-line)] px-3 py-1.5 font-mono text-[10px] tracking-[0.2em] uppercase gap-2 flex-wrap">
        <span className="text-[var(--color-ink-faint)] tab-num shrink-0">
          № {String(index + 1).padStart(3, "0")}
        </span>
        <div className="flex items-center gap-2 flex-wrap justify-end flex-1">
          <span
            className={
              "px-2 py-0.5 font-mono text-[10px] tracking-[0.15em] uppercase shrink-0 " +
              summaryStyles
            }
          >
            {summary}
            {discovery.bad_count > 0 ? ` · ${discovery.bad_count} BAD` : ""}
            {discovery.warn_count > 0 ? ` · ${discovery.warn_count} WATCH` : ""}
          </span>
          {profile.cto && (
            <span className="px-1.5 py-0.5 bg-[var(--color-amber)] text-[var(--color-bg)] shrink-0">
              CTO
            </span>
          )}
          <span className="text-[var(--color-ink-dim)] shrink-0">
            {profile.chainId}
          </span>
          {item.pair?.dexId && (
            <span className="text-[var(--color-ink-faint)] normal-case tracking-normal shrink-0 hidden sm:inline">
              {item.pair.dexId}
            </span>
          )}
        </div>
      </div>

      {pipe ? (
        <div className="relative z-[30] pointer-events-auto px-3 py-1.5 border-b border-[var(--color-line)] bg-[var(--color-bg)] font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--color-ink-dim)] flex flex-wrap gap-x-3 gap-y-1">
          <span className="text-[var(--color-acid)]">
            SIG {pipe.signal_score ?? "—"}
          </span>
          <span>RISK · {pipe.risk_label ?? "—"}</span>
          <span>
            MVP ·{" "}
            {pipe.market_all_pass ? (
              <span className="text-[var(--color-acid)]">PASS</span>
            ) : (
              <span className="text-[var(--color-blood)]">FAIL</span>
            )}
          </span>
          <span>
            ALERT ELIGIBLE ·{" "}
            <span className={pipe.eligible_for_trade_alert ? "text-[var(--color-acid)]" : ""}>
              {pipe.eligible_for_trade_alert ? "YES" : "NO"}
            </span>
          </span>
        </div>
      ) : null}

      {pair_fetch_error && (
        <div className="px-3 py-1 font-mono text-[10px] text-[var(--color-blood)] border-b border-[var(--color-line)] tracking-[0.12em] uppercase bg-[var(--color-bg)]">
          Pair fetch: {pair_fetch_error}
        </div>
      )}

      <div className="px-3 py-2 border-b border-[var(--color-line)] bg-[var(--color-bg)]">
        <div className="font-mono text-[9px] tracking-[0.28em] uppercase text-[var(--color-ink-faint)] mb-2">
          Discovery metrics
        </div>
        <div className="grid grid-cols-2 gap-px bg-[var(--color-line)]">
          <MetricCell label="Liquidity" value={fmtUsd(m.liquidity_usd)} />
          <MetricCell label="Vol h1" value={fmtUsd(m.volume_h1)} />
          <MetricCell
            label="Tx h1"
            value={
              m.txns_h1_total != null
                ? `${m.txns_h1_total} (${m.buys_h1 ?? 0}B/${m.sells_h1 ?? 0}S)`
                : "—"
            }
          />
          <MetricCell label="Buy/sell" value={fmtRatio(m.buy_sell_ratio_h1)} />
          <MetricCell label="Pair age" value={fmtAgeHours(m.pair_age_hours)} />
          <MetricCell label="FDV" value={fmtUsd(m.fdv)} />
          <MetricCell label="Δ m5" value={fmtPct(m.price_change_m5)} />
          <MetricCell label="Δ h1" value={fmtPct(m.price_change_h1)} />
        </div>

        {(discovery.flags.length > 0 || positives.length > 0) && (
          <div className="mt-2 flex flex-wrap gap-1">
            {discovery.flags.map((f, i) => (
              <span
                key={`${f.key}-${i}`}
                className={
                  "font-mono text-[9px] tracking-[0.14em] uppercase px-1.5 py-0.5 " +
                  (f.severity === "bad"
                    ? "bg-[var(--color-blood)] text-[var(--color-bg)]"
                    : "border border-[var(--color-amber)] text-[var(--color-amber)]")
                }
              >
                {f.label}
              </span>
            ))}
            {positives.map((p, i) => (
              <span
                key={`${p.key}-${i}`}
                className="font-mono text-[9px] tracking-[0.14em] uppercase px-1.5 py-0.5 border border-[var(--color-acid-dim)] text-[var(--color-acid)]"
              >
                {p.label}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="relative aspect-[3/1] bg-[var(--color-bg-3)] overflow-hidden">
        {banner ? (
          <img
            src={banner}
            alt=""
            loading="lazy"
            className="w-full h-full object-cover opacity-90 group-hover:opacity-100 group-hover:scale-[1.02] transition-all duration-500"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-[var(--color-ink-faint)] font-mono text-[10px] tracking-[0.3em]">
            NO SIGNAL
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-[var(--color-bg-2)] via-transparent to-transparent" />
        {profile.icon && (
          <div className="absolute -bottom-px left-3 w-12 h-12 hairline-strong bg-[var(--color-bg-3)] overflow-hidden">
            <img
              src={profile.icon}
              alt=""
              loading="lazy"
              className="w-full h-full object-cover"
            />
          </div>
        )}
      </div>

      <div className="px-3 pt-4 pb-3">
        <div className="flex items-start justify-between gap-3 mb-3">
          <button
            type="button"
            onClick={copy}
            title="Copy address"
            className="relative z-[40] pointer-events-auto font-mono text-[11px] text-[var(--color-ink-dim)] hover:text-[var(--color-acid)] tracking-tight text-left"
          >
            {copied ? "COPIED ✓" : shortAddress(profile.tokenAddress)}
          </button>
          <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--color-ink-faint)] tab-num shrink-0">
            {timeAgo(profile.updatedAt)} ago
          </span>
        </div>

        <p className="font-display text-[19px] leading-[1.25] text-balance text-[var(--color-ink)] clamp-3 min-h-[3.75em]">
          {profile.description || (
            <span className="text-[var(--color-ink-faint)] italic">
              No transmission attached.
            </span>
          )}
        </p>

        {profile.links && profile.links.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {profile.links.map((link, i) => (
              <span
                key={i}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    window.open(link.url, "_blank", "noopener,noreferrer");
                  }
                }}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  window.open(link.url, "_blank", "noopener,noreferrer");
                }}
                className="relative z-[40] cursor-pointer pointer-events-auto font-mono text-[10px] tracking-[0.18em] uppercase px-2 py-1 border border-[var(--color-line)] text-[var(--color-ink-dim)] hover:border-[var(--color-acid)] hover:text-[var(--color-acid)] transition-colors"
              >
                [{linkCode(link)}]
              </span>
            ))}
          </div>
        )}
      </div>

        {buyUrl && (
          <div className="relative z-[40] px-3 pt-3 pointer-events-auto">
            <a
              href={buyUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => {
                e.stopPropagation();
              }}
              className="inline-flex items-center gap-2 font-mono text-[10px] tracking-[0.2em] uppercase px-3 py-1.5 border border-[var(--color-acid-dim)] text-[var(--color-acid)] hover:bg-[var(--color-acid)] hover:text-[var(--color-bg)] transition-colors"
            >
              Buy preview (Jupiter) ↗
            </a>
            <span className="block mt-2 font-mono text-[9px] text-[var(--color-ink-faint)] normal-case tracking-normal">
              Opens Jupiter UI — Phantom routing lands in v3/v4 infra.
            </span>
          </div>
        )}

      <div className="flex items-center justify-between border-t border-[var(--color-line)] px-3 py-2 font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--color-ink-faint)]">
        <span>{item.pair?.pairAddress ? "open pair" : "view on dex"}</span>
        <span className="text-[var(--color-ink-dim)] group-hover:text-[var(--color-acid)] transition-colors">
          ↗
        </span>
      </div>
      </div>
    </div>
  );
}
