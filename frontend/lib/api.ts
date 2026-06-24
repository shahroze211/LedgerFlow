import type {
  AuditEntry,
  Invoice,
  InvoiceSummary,
  Stats,
  Status,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = await res.text();
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
}

export const api = {
  base: BASE,
  stats: () => j<Stats>("/stats"),
  listInvoices: (status?: Status) =>
    j<InvoiceSummary[]>(`/invoices${status ? `?status=${status}` : ""}`),
  reviewQueue: () => j<InvoiceSummary[]>("/review/queue"),
  getInvoice: (id: string) => j<Invoice>(`/invoices/${id}`),
  getAudit: (id: string) => j<AuditEntry[]>(`/invoices/${id}/audit`),
  documentUrl: (id: string) => `${BASE}/invoices/${id}/document`,

  approve: (id: string, edits: Record<string, unknown>, reviewer: string) =>
    j<Invoice>(`/review/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ edits, reviewer }),
    }),

  requeue: (id: string) =>
    j<Invoice>(`/review/${id}/requeue`, { method: "POST" }),

  upload: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/ingest/upload`, { method: "POST", body: form });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.json();
  },
};
