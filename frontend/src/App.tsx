import { useEffect, useMemo, useState, useCallback } from "react";
import { fetchDiscoveryFeed } from "./api";
import type { FeedItem, FeedMeta } from "./types";
import { Marquee } from "./components/Marquee";
import { ChainFilter } from "./components/ChainFilter";
import { TokenCard } from "./components/TokenCard";

type Status = "idle" | "loading" | "ready" | "error";

function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

function fmtClock(d: Date): string {
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`;
}

function dedupeFeedItems(items: FeedItem[]): FeedItem[] {
  const seen = new Set<string>();
  const out: FeedItem[] = [];
  for (const it of items) {
    const k = `${it.profile.chainId}:${it.profile.tokenAddress.toLowerCase()}`;
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(it);
  }
  return out;
}

export default function App() {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [deckRevision, setDeckRevision] = useState(0);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [chain, setChain] = useState<string>("all");
  const [query, setQuery] = useState<string>("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [feedMeta, setFeedMeta] = useState<FeedMeta | null>(null);
  const now = useNow(1000);

  const load = useCallback(async (shuffleDeck = false) => {
    setStatus("loading");
    setError(null);
    try {
      const data = await fetchDiscoveryFeed();
      setFeedMeta(data.feed_meta ?? null);
      const next = shuffleDeck ? shuffle(data.items) : data.items;
      setItems(dedupeFeedItems(next));
      if (shuffleDeck) setDeckRevision((r) => r + 1);
      setLastUpdated(new Date());
      setStatus("ready");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    void load(true);
    const id = setInterval(() => void load(false), 60_000);
    return () => clearInterval(id);
  }, [load]);

  const chainCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const it of items) {
      counts.set(it.profile.chainId, (counts.get(it.profile.chainId) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .map(([id, count]) => ({ id, count }))
      .sort((a, b) => b.count - a.count);
  }, [items]);

  const badSignals = useMemo(
    () => items.filter((it) => it.discovery.overall_bad).length,
    [items],
  );

  const filtered = useMemo(() => {
    let list = items;
    if (chain !== "all")
      list = list.filter((it) => it.profile.chainId === chain);
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      list = list.filter(
        (it) =>
          it.profile.tokenAddress.toLowerCase().includes(q) ||
          (it.profile.description ?? "").toLowerCase().includes(q),
      );
    }
    return list;
  }, [items, chain, query]);

  const marqueeItems = useMemo(() => {
    const head = [
      "CORTISOL // TOKEN SURVEILLANCE TERMINAL",
      "DEDUPED // RECENT + BOOSTS + CTO + ADS + LATEST",
      "PAIR DATA · DISCOVERY RUBRIC",
      "SOURCE DEXSCREENER.COM",
      "EST 2026",
    ];
    const samples = items.slice(0, 8).map(
      (it) =>
        `${it.profile.chainId.toUpperCase()} / ${it.profile.tokenAddress.slice(0, 6)}…${it.profile.tokenAddress.slice(-4)}`,
    );
    return [...head, ...samples];
  }, [items]);

  return (
    <div className="grain scanlines min-h-full">
      <Marquee items={marqueeItems} />

      <header className="relative border-b border-[var(--color-line)]">
        <div className="mx-auto max-w-[1400px] px-6 md:px-10 py-10 md:py-16">
          <div className="grid grid-cols-12 gap-6 items-end">
            <div className="col-span-12 md:col-span-8">
              <div className="flex items-center gap-3 mb-6 font-mono text-[11px] tracking-[0.24em] uppercase text-[var(--color-ink-faint)]">
                <span className="inline-flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-acid)] pulse-dot" />
                  <span className="text-[var(--color-ink-dim)]">
                    Signal acquired
                  </span>
                </span>
                
               
              </div>
              <h1 className="font-display text-[88px] md:text-[148px] leading-[0.88] tracking-[-0.02em] text-[var(--color-ink)]">
                Cortisol
                <span className="text-[var(--color-acid)]">.</span>
              </h1>
             
            </div>

            <div className="col-span-12 md:col-span-4 md:justify-self-end w-full md:w-auto">
              <div className="hairline bg-[var(--color-bg-2)] p-4 font-mono text-[11px] tracking-[0.16em] uppercase">
                <Row label="Clock" value={fmtClock(now)} mono accent />
                <Row
                  label="Updated"
                  value={
                    lastUpdated
                      ? `${Math.max(0, Math.floor((now.getTime() - lastUpdated.getTime()) / 1000))}s ago`
                      : "—"
                  }
                  mono
                />
                <Row
                  label="Signals"
                  value={items.length.toString().padStart(3, "0")}
                  mono
                />
                <Row
                  label="Dex merge"
                  value={
                    feedMeta?.unique_tokens != null
                      ? feedMeta.unique_tokens.toString().padStart(3, "0")
                      : "—"
                  }
                  mono
                  warn={Boolean(feedMeta?.sources_failed)}
                />
                <Row
                  label="Math filter"
                  value={
                    feedMeta?.mvp_math_pass_only
                      ? `${(feedMeta.items_after_mvp_filter ?? 0)
                          .toString()
                          .padStart(2, "0")}/${(
                          feedMeta.items_before_mvp_filter ?? 0
                        )
                          .toString()
                          .padStart(2, "0")} MVP`
                      : "Off"
                  }
                  mono
                />
                <Row
                  label="Bad"
                  value={badSignals.toString().padStart(3, "0")}
                  mono
                  warn={badSignals > 0}
                />
                <Row
                  label="Status"
                  value={
                    status === "ready"
                      ? "Nominal"
                      : status === "loading"
                        ? "Polling…"
                        : status === "error"
                          ? "Error"
                          : "Idle"
                  }
                  mono
                  warn={status === "error"}
                />
                <button
                  onClick={() => void load(true)}
                  disabled={status === "loading"}
                  className="mt-3 w-full text-left px-3 py-2 border border-[var(--color-acid)] text-[var(--color-acid)] hover:bg-[var(--color-acid)] hover:text-[var(--color-bg)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-between"
                >
                  <span>Repoll feed</span>
                  <span>↻</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>

      <section className="border-b border-[var(--color-line)]">
        <div className="mx-auto max-w-[1400px] px-6 md:px-10 py-5 flex flex-col md:flex-row gap-5 md:items-center md:justify-between">
          <ChainFilter
            chains={chainCounts}
            active={chain}
            onChange={setChain}
            total={items.length}
          />
          <div className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.16em]">
            <span className="text-[var(--color-ink-faint)]">Search /</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="ADDRESS OR KEYWORD"
              className="bg-transparent border border-[var(--color-line)] focus:border-[var(--color-acid)] outline-none px-3 py-1.5 w-64 placeholder:text-[var(--color-ink-faint)] text-[var(--color-ink)] tracking-[0.12em]"
            />
          </div>
        </div>
      </section>

      <main className="mx-auto max-w-[1400px] px-6 md:px-10 py-8 md:py-12">
        <div className="flex items-center justify-between mb-6 font-mono text-[11px] tracking-[0.2em] uppercase text-[var(--color-ink-faint)]">
          <span>02 / Incoming transmissions</span>
          <span className="tab-num">
            {filtered.length.toString().padStart(3, "0")} /{" "}
            {items.length.toString().padStart(3, "0")}
          </span>
        </div>

        {status === "loading" && items.length === 0 && <SkeletonGrid />}

        {status === "error" && (
          <div className="hairline border-[var(--color-blood)] bg-[var(--color-bg-2)] p-6 font-mono text-[12px] text-[var(--color-blood)]">
            <div className="text-[10px] tracking-[0.3em] uppercase mb-2">
              ▌ Transmission lost
            </div>
            <div className="text-[var(--color-ink-dim)]">{error}</div>
          </div>
        )}

        {status === "ready" &&
          items.length === 0 &&
          feedMeta?.mvp_math_pass_only &&
          (feedMeta.items_before_mvp_filter ?? 0) > 0 && (
            <div className="hairline border-[var(--color-line-strong)] bg-[var(--color-bg-2)] p-6 mb-8 font-mono text-[11px] text-[var(--color-ink-dim)] tracking-[0.14em]">
              <div className="uppercase text-[var(--color-ink-faint)] mb-2">
                No MVP-pass tokens this poll
              </div>
              <p className="text-[10px] leading-relaxed max-w-xl">
                The grid only shows rows that pass all market gates (liquidity floor, 1h
                volume floor, buy pressure vs sells, known pair). The Dex merge had{" "}
                <span className="text-[var(--color-acid)] tab-num">
                  {feedMeta.items_before_mvp_filter}
                </span>{" "}
                profiles; none met that bar. Set{" "}
                <span className="text-[var(--color-acid)]">
                  CORTISOL_FEED_MATH_PASS_ONLY=0
                </span>{" "}
                in backend{" "}
                <span className="text-[var(--color-acid)]">.env</span> or call the API
                with{" "}
                <span className="text-[var(--color-acid)]">mvp_pass_only=false</span> to
                see the full list.
              </p>
            </div>
          )}

        {status === "ready" &&
          items.length === 0 &&
          feedMeta?.upstream_errors &&
          feedMeta.upstream_errors.length > 0 && (
            <div className="hairline border-[var(--color-line-strong)] bg-[var(--color-bg-2)] p-6 mb-8 font-mono text-[11px] text-[var(--color-ink-dim)] tracking-[0.14em]">
              <div className="uppercase text-[var(--color-ink-faint)] mb-2">
                Upstream paused (often HTTP 429)
              </div>
              <pre className="whitespace-pre-wrap text-[10px] leading-relaxed opacity-90">
                {feedMeta.upstream_errors
                  .map((e) => `${e.source}: ${e.detail}`)
                  .slice(0, 4)
                  .join("\n")}
              </pre>
              <p className="mt-3 text-[var(--color-ink-faint)] uppercase text-[10px]">
                Try Repoll in ~60s or increase{" "}
                <span className="text-[var(--color-acid)]">CORTISOL_DEX_LIST_PAUSE_SECONDS</span>{" "}
                in backend .env (see README).
              </p>
            </div>
          )}

        {status !== "error" && filtered.length === 0 && items.length > 0 && (
          <div className="hairline bg-[var(--color-bg-2)] p-10 text-center font-mono text-[11px] tracking-[0.2em] uppercase text-[var(--color-ink-faint)]">
            No matching profiles in the feed.
          </div>
        )}

        {filtered.length > 0 && (
          <div
            key={deckRevision}
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-px bg-[var(--color-line)]"
          >
            {filtered.map((it, i) => (
              <div
                key={`${it.profile.chainId}:${it.profile.tokenAddress.toLowerCase()}`}
                className="bg-[var(--color-bg)]"
              >
                <TokenCard item={it} index={i} />
              </div>
            ))}
          </div>
        )}
      </main>

      <footer className="border-t border-[var(--color-line)]">
        <div className="mx-auto max-w-[1400px] px-6 md:px-10 py-6 flex flex-col md:flex-row md:items-center md:justify-between gap-2 font-mono text-[10px] tracking-[0.22em] uppercase text-[var(--color-ink-faint)]">
          <span>
            Cortisol{" "}
            <span className="text-[var(--color-ink-dim)]">v0.2.0</span> &mdash;
            data via Dexscreener
          </span>
          <span>
            ⓒ &nbsp;Surveillance is not endorsement. Do your own research.
          </span>
        </div>
      </footer>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
  accent,
  warn,
}: {
  label: string;
  value: string;
  mono?: boolean;
  accent?: boolean;
  warn?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 border-b last:border-b-0 border-[var(--color-line)]">
      <span className="text-[var(--color-ink-faint)]">{label}</span>
      <span
        className={
          (mono ? "tab-num " : "") +
          (accent
            ? "text-[var(--color-acid)]"
            : warn
              ? "text-[var(--color-blood)]"
              : "text-[var(--color-ink)]")
        }
      >
        {value}
      </span>
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-px bg-[var(--color-line)]">
      {Array.from({ length: 9 }).map((_, i) => (
        <div
          key={i}
          className="bg-[var(--color-bg-2)] hairline animate-pulse min-h-[520px]"
          style={{ animationDelay: `${i * 80}ms` }}
        />
      ))}
    </div>
  );
}
