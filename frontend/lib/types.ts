export type Status =
  | "queued"
  | "extracting"
  | "needs_review"
  | "auto_approved"
  | "approved"
  | "synced"
  | "dead_letter";

export const HEADLINE_FIELDS = [
  "vendor",
  "invoice_number",
  "invoice_date",
  "currency",
  "subtotal",
  "tax",
  "total",
] as const;

export type HeadlineField = (typeof HEADLINE_FIELDS)[number];

export interface ValidationCheck {
  rule: string;
  passed: boolean;
  severity: string;
  message: string;
  fields: string[];
}

export interface LineItem {
  description: string | null;
  qty: number | null;
  unit_price: number | null;
  amount: number | null;
  confidence: number | null;
}

export interface Invoice {
  id: string;
  content_hash: string;
  source_ref: string;
  original_filename: string | null;
  status: Status;
  attempts: number;
  vendor: string | null;
  vendor_account_code: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  currency: string | null;
  subtotal: number | null;
  tax: number | null;
  total: number | null;
  field_confidence: Record<string, number> | null;
  field_sources: Record<string, string> | null;
  validation_results: ValidationCheck[] | null;
  gate_reason: string | null;
  approved_by: string | null;
  error: string | null;
  line_items: LineItem[];
  created_at: string;
  updated_at: string;
}

export interface InvoiceSummary {
  id: string;
  status: Status;
  vendor: string | null;
  invoice_number: string | null;
  total: number | null;
  currency: string | null;
  gate_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface Stats {
  total: number;
  by_status: Record<string, number>;
  auto_approval_rate: number;
  needs_review: number;
  downstream_records: number;
  duplicate_writes_prevented: number;
  confidence_threshold: number;
}

export interface AuditEntry {
  event: string;
  from_status: string | null;
  to_status: string | null;
  actor: string;
  detail: Record<string, unknown> | null;
  created_at: string;
}
