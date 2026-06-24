"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Invoice, InvoiceSummary, Stats } from "@/lib/types";
import { StatsBar } from "@/components/StatsBar";
import { InvoiceList } from "@/components/InvoiceList";
import { ReviewPanel } from "@/components/ReviewPanel";

type Tab = "review" | "all";

export default function Page() {
  const [tab, setTab] = useState<Tab>("review");
  const [stats, setStats] = useState<Stats | null>(null);
  const [items, setItems] = useState<InvoiceSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Invoice | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    const [s, list] = await Promise.all([
      api.stats(),
      tab === "review" ? api.reviewQueue() : api.listInvoices(),
    ]);
    setStats(s);
    setItems(list);
    setSelectedId((cur) => cur ?? (list[0]?.id ?? null));
  }, [tab]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      return;
    }
    api.getInvoice(selectedId).then(setSelected).catch(() => setSelected(null));
  }, [selectedId, items]);

  async function onUpload(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const res = await api.upload(file);
        if (!res.duplicate) setSelectedId(res.invoice_id);
      }
      await refresh();
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-5 py-6">
      <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">
            LedgerFlow <span className="text-gray-500">· invoice intake</span>
          </h1>
          <p className="text-sm text-gray-500">
            Confident invoices sync themselves. The rest land here for a 5-second human fix.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".txt,.md,.csv,.pdf"
            className="hidden"
            onChange={(e) => onUpload(e.target.files)}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="rounded-md border border-edge bg-panel px-4 py-2 text-sm font-medium text-gray-200 hover:border-gray-500 disabled:opacity-50"
          >
            {uploading ? "Uploading…" : "Upload invoice"}
          </button>
        </div>
      </header>

      <StatsBar stats={stats} />

      <div className="mt-5 flex gap-2">
        {(["review", "all"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              setSelectedId(null);
            }}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
              tab === t
                ? "bg-sky-600 text-white"
                : "border border-edge bg-panel text-gray-400 hover:text-gray-200"
            }`}
          >
            {t === "review" ? `Review queue${stats ? ` (${stats.needs_review})` : ""}` : "All invoices"}
          </button>
        ))}
      </div>

      <div className="mt-3 grid gap-4 lg:grid-cols-[340px_1fr]">
        <div className="max-h-[78vh] overflow-auto pr-1">
          <InvoiceList
            items={items}
            selectedId={selectedId}
            onSelect={setSelectedId}
            emptyHint={
              tab === "review"
                ? "Nothing to review — the gate is keeping the queue empty. 🎉"
                : "No invoices yet. Upload one to get started."
            }
          />
        </div>

        <div>
          {selected && stats ? (
            <ReviewPanel
              invoice={selected}
              threshold={stats.confidence_threshold}
              reviewer="reviewer"
              onChanged={refresh}
            />
          ) : (
            <div className="flex h-[300px] items-center justify-center rounded-lg border border-dashed border-edge text-sm text-gray-600">
              Select an invoice to inspect it.
            </div>
          )}
        </div>
      </div>

      <footer className="mt-8 text-center text-xs text-gray-600">
        API: {api.base} · provider-agnostic extraction · deterministic gate · idempotent sync
      </footer>
    </main>
  );
}
