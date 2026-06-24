import type { InvoiceSummary } from "@/lib/types";
import { Badge } from "./Badge";

export function InvoiceList({
  items,
  selectedId,
  onSelect,
  emptyHint,
}: {
  items: InvoiceSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  emptyHint: string;
}) {
  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-edge px-4 py-10 text-center text-sm text-gray-500">
        {emptyHint}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {items.map((inv) => (
        <button
          key={inv.id}
          onClick={() => onSelect(inv.id)}
          className={`w-full rounded-lg border px-3 py-2.5 text-left transition ${
            selectedId === inv.id
              ? "border-sky-600 bg-sky-950/40"
              : "border-edge bg-panel hover:border-gray-600"
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="truncate font-medium text-gray-100">
              {inv.vendor || <span className="text-gray-500">(no vendor)</span>}
            </span>
            <Badge status={inv.status} />
          </div>
          <div className="mt-1 flex items-center justify-between text-xs text-gray-500">
            <span className="font-mono">{inv.invoice_number || inv.id}</span>
            <span>
              {inv.total != null
                ? `${inv.currency || ""} ${inv.total.toLocaleString()}`
                : "—"}
            </span>
          </div>
          {inv.status === "needs_review" && inv.gate_reason && (
            <div className="mt-1 truncate text-xs text-amber-400/80" title={inv.gate_reason}>
              {inv.gate_reason}
            </div>
          )}
        </button>
      ))}
    </div>
  );
}
