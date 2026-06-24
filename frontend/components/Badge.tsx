import type { Status } from "@/lib/types";

const STYLES: Record<Status, string> = {
  queued: "bg-gray-700/40 text-gray-300 border-gray-600",
  extracting: "bg-blue-900/40 text-blue-300 border-blue-700",
  needs_review: "bg-amber-900/40 text-amber-300 border-amber-600",
  auto_approved: "bg-emerald-900/40 text-emerald-300 border-emerald-700",
  approved: "bg-emerald-900/40 text-emerald-300 border-emerald-700",
  synced: "bg-emerald-700/30 text-emerald-200 border-emerald-600",
  dead_letter: "bg-red-900/50 text-red-300 border-red-700",
};

const LABELS: Record<Status, string> = {
  queued: "Queued",
  extracting: "Extracting",
  needs_review: "Needs review",
  auto_approved: "Auto-approved",
  approved: "Approved",
  synced: "Synced",
  dead_letter: "Dead-letter",
};

export function Badge({ status }: { status: Status }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}
    >
      {LABELS[status]}
    </span>
  );
}
