interface ChainCount {
  id: string;
  count: number;
}

interface ChainFilterProps {
  chains: ChainCount[];
  active: string;
  onChange: (chain: string) => void;
  total: number;
}

export function ChainFilter({
  chains,
  active,
  onChange,
  total,
}: ChainFilterProps) {
  const all = { id: "all", count: total };
  const list = [all, ...chains];
  return (
    <div className="flex flex-wrap items-center gap-x-1 gap-y-2 font-mono text-[11px] uppercase tracking-[0.16em]">
      <span className="text-[var(--color-ink-faint)] mr-2">FILTER /</span>
      {list.map((c) => {
        const isActive = active === c.id;
        return (
          <button
            key={c.id}
            onClick={() => onChange(c.id)}
            className={
              "group inline-flex items-center gap-2 px-3 py-1.5 border transition-colors " +
              (isActive
                ? "border-[var(--color-acid)] bg-[var(--color-acid)] text-[var(--color-bg)]"
                : "border-[var(--color-line)] text-[var(--color-ink-dim)] hover:text-[var(--color-ink)] hover:border-[var(--color-line-strong)]")
            }
          >
            <span>{c.id}</span>
            <span
              className={
                "tab-num text-[10px] " +
                (isActive
                  ? "text-[var(--color-bg)]/70"
                  : "text-[var(--color-ink-faint)]")
              }
            >
              {c.count.toString().padStart(2, "0")}
            </span>
          </button>
        );
      })}
    </div>
  );
}
