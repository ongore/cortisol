interface MarqueeProps {
  items: string[];
}

export function Marquee({ items }: MarqueeProps) {
  const stream = [...items, ...items];
  return (
    <div className="relative z-10 border-b border-[var(--color-line)] bg-[var(--color-bg-2)] overflow-hidden">
      <div className="flex items-center">
        <div className="shrink-0 px-3 py-1.5 text-[10px] tracking-[0.2em] font-mono uppercase bg-[var(--color-acid)] text-[var(--color-bg)] font-semibold">
          LIVE
        </div>
        <div className="overflow-hidden flex-1">
          <div className="marquee-track flex whitespace-nowrap py-1.5 text-[11px] tracking-[0.18em] font-mono uppercase text-[var(--color-ink-dim)]">
            {stream.map((item, i) => (
              <span key={i} className="px-6 inline-flex items-center gap-3">
                <span className="text-[var(--color-acid)]">&raquo;</span>
                <span>{item}</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
