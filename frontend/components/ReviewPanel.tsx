"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { HEADLINE_FIELDS, type HeadlineField, type Invoice } from "@/lib/types";
import { Badge } from "./Badge";

const NUMERIC: HeadlineField[] = ["subtotal", "tax", "total"];
const LABELS: Record<HeadlineField, string> = {
  vendor: "Vendor",
  invoice_number: "Invoice #",
  invoice_date: "Invoice date",
  currency: "Currency",
  subtotal: "Subtotal",
  tax: "Tax",
  total: "Total",
};

export function ReviewPanel({
  invoice,
  threshold,
  reviewer,
  onChanged,
}: {
  invoice: Invoice;
  threshold: number;
  reviewer: string;
  onChanged: () => void;
}) {
  const [doc, setDoc] = useState<string>("");
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setEdits({});
    setError(null);
    fetch(api.documentUrl(invoice.id))
      .then((r) => (r.ok ? r.text() : "(original document unavailable)"))
      .then(setDoc)
      .catch(() => setDoc("(original document unavailable)"));
  }, [invoice.id]);

  const failedFields = useMemo(() => {
    const s = new Set<string>();
    (invoice.validation_results || [])
      .filter((c) => !c.passed && c.severity === "error")
      .forEach((c) => c.fields.forEach((f) => s.add(f)));
    return s;
  }, [invoice]);

  const conf = invoice.field_confidence || {};
  const isLowConf = (f: string) => (conf[f] ?? 0) < threshold;
  const isFlagged = (f: string) => isLowConf(f) || failedFields.has(f);

  const valueOf = (f: HeadlineField): string => {
    if (f in edits) return edits[f];
    const v = invoice[f];
    return v == null ? "" : String(v);
  };

  const canApprove = invoice.status === "needs_review";

  async function approve() {
    setBusy(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {};
      for (const f of HEADLINE_FIELDS) {
        if (f in edits) {
          const raw = edits[f].trim();
          payload[f] = raw === "" ? null : NUMERIC.includes(f) ? Number(raw) : raw;
        }
      }
      await api.approve(invoice.id, payload, reviewer);
      onChanged();
    } catch (e) {
      if (e instanceof ApiError && e.detail && typeof e.detail === "object") {
        const d = e.detail as { message?: string; failed?: { message: string }[] };
        setError(
          [d.message, ...(d.failed || []).map((x) => `• ${x.message}`)]
            .filter(Boolean)
            .join("\n"),
        );
      } else {
        setError(String((e as Error).message));
      }
    } finally {
      setBusy(false);
    }
  }

  async function requeue() {
    setBusy(true);
    try {
      await api.requeue(invoice.id);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-edge bg-panel">
      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-edge px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm text-gray-400">{invoice.id}</span>
          <Badge status={invoice.status} />
          {invoice.vendor_account_code && (
            <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400">
              {invoice.vendor_account_code}
            </span>
          )}
        </div>
        {invoice.approved_by && (
          <span className="text-xs text-gray-500">approved by {invoice.approved_by}</span>
        )}
      </div>

      {invoice.gate_reason && (
        <div className="border-b border-edge bg-amber-950/20 px-4 py-2 text-sm text-amber-300/90">
          {invoice.gate_reason}
        </div>
      )}

      <div className="grid gap-4 p-4 lg:grid-cols-2">
        {/* original document */}
        <div>
          <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">
            Original document
          </div>
          <pre className="h-[420px] overflow-auto rounded-md border border-edge bg-ink p-3 text-xs leading-relaxed text-gray-300">
            {doc}
          </pre>
        </div>

        {/* extracted fields */}
        <div>
          <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-wide text-gray-500">
            <span>Extracted fields</span>
            <span className="normal-case text-gray-600">
              edit a flagged field, then approve
            </span>
          </div>
          <div className="space-y-2">
            {HEADLINE_FIELDS.map((f) => {
              const flagged = isFlagged(f);
              const c = conf[f];
              return (
                <div key={f} className="flex items-center gap-2">
                  <label className="w-24 shrink-0 text-xs text-gray-500">{LABELS[f]}</label>
                  <input
                    value={valueOf(f)}
                    disabled={!canApprove}
                    onChange={(e) => setEdits((p) => ({ ...p, [f]: e.target.value }))}
                    className={`flex-1 rounded-md border bg-ink px-2 py-1.5 text-sm outline-none focus:ring-1 ${
                      flagged
                        ? "border-amber-600/70 text-amber-100 focus:ring-amber-500"
                        : "border-edge text-gray-200 focus:ring-sky-600"
                    } disabled:opacity-70`}
                  />
                  <span
                    className={`w-12 shrink-0 text-right text-xs ${
                      c == null
                        ? "text-gray-600"
                        : isLowConf(f)
                          ? "text-amber-400"
                          : "text-emerald-400"
                    }`}
                    title="model confidence"
                  >
                    {c == null ? "—" : `${(c * 100).toFixed(0)}%`}
                  </span>
                </div>
              );
            })}
          </div>

          {/* line items */}
          {invoice.line_items.length > 0 && (
            <div className="mt-4">
              <div className="mb-1 text-xs uppercase tracking-wide text-gray-500">
                Line items
              </div>
              <div className="overflow-hidden rounded-md border border-edge text-xs">
                {invoice.line_items.map((li, i) => (
                  <div
                    key={i}
                    className="flex justify-between border-b border-edge/60 px-2 py-1 last:border-0"
                  >
                    <span className="truncate text-gray-300">{li.description}</span>
                    <span className="ml-2 shrink-0 font-mono text-gray-400">
                      {li.qty} × {li.unit_price} = {li.amount}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* validation results */}
      <div className="border-t border-edge px-4 py-3">
        <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">
          Deterministic validations
        </div>
        <div className="grid gap-1 sm:grid-cols-2">
          {(invoice.validation_results || []).map((c) => (
            <div key={c.rule} className="flex items-start gap-2 text-xs">
              <span className={c.passed ? "text-emerald-400" : "text-red-400"}>
                {c.passed ? "✓" : "✕"}
              </span>
              <span className={c.passed ? "text-gray-400" : "text-red-300"}>{c.message}</span>
            </div>
          ))}
        </div>
      </div>

      {/* actions */}
      <div className="flex flex-wrap items-center gap-3 border-t border-edge px-4 py-3">
        {canApprove && (
          <button
            onClick={approve}
            disabled={busy}
            className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            {busy ? "Approving…" : "Approve & sync"}
          </button>
        )}
        {invoice.status === "dead_letter" && (
          <button
            onClick={requeue}
            disabled={busy}
            className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {busy ? "Requeuing…" : "Requeue"}
          </button>
        )}
        {invoice.status === "synced" && (
          <span className="text-sm text-emerald-400">✓ Written downstream exactly once.</span>
        )}
        {error && (
          <pre className="whitespace-pre-wrap text-xs text-red-400">{error}</pre>
        )}
      </div>
    </div>
  );
}
