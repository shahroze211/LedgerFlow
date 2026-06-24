import type { Stats } from "@/lib/types";

function Metric({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-edge bg-panel px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${accent || "text-gray-100"}`}>{value}</div>
      {sub && <div className="text-xs text-gray-500">{sub}</div>}
    </div>
  );
}

export function StatsBar({ stats }: { stats: Stats | null }) {
  if (!stats) {
    return <div className="h-[84px] animate-pulse rounded-lg border border-edge bg-panel" />;
  }
  const pct = (n: number) => `${(n * 100).toFixed(0)}%`;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <Metric label="Invoices" value={String(stats.total)} sub="ingested" />
      <Metric
        label="Auto-approval"
        value={pct(stats.auto_approval_rate)}
        sub={`gate ≥ ${pct(stats.confidence_threshold)} conf`}
        accent="text-emerald-300"
      />
      <Metric
        label="Needs review"
        value={String(stats.needs_review)}
        sub="awaiting a human"
        accent={stats.needs_review ? "text-amber-300" : "text-gray-100"}
      />
      <Metric label="Synced downstream" value={String(stats.downstream_records)} sub="exactly once" />
      <Metric
        label="Dupes prevented"
        value={String(stats.duplicate_writes_prevented)}
        sub="idempotent writes"
        accent="text-sky-300"
      />
    </div>
  );
}
