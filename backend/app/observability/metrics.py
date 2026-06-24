"""Prometheus metrics (P7).

These are the numbers the demo dashboard is built from: throughput, auto-approval
rate, latency, errors, dead-letters, and the drift signal (a sustained rise in the
low-confidence rate means the input distribution shifted and the human queue will
grow).
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# --- throughput & outcomes ------------------------------------------------- #
invoices_processed_total = Counter(
    "ledgerflow_invoices_processed_total",
    "Invoices that completed the extract->validate->gate pipeline.",
    ["outcome"],  # auto_approved | needs_review
)
invoices_ingested_total = Counter(
    "ledgerflow_invoices_ingested_total",
    "Invoices accepted at ingest.",
    ["duplicate"],  # true | false
)
invoices_synced_total = Counter(
    "ledgerflow_invoices_synced_total",
    "Successful downstream writes.",
    ["created"],  # true (first write) | false (idempotent repeat)
)

# --- reliability ----------------------------------------------------------- #
extraction_errors_total = Counter(
    "ledgerflow_extraction_errors_total",
    "Extraction attempts that raised (pre-retry).",
)
dead_letter_total = Counter(
    "ledgerflow_dead_letter_total",
    "Jobs that exhausted retries and were dead-lettered (P4).",
)

# --- latency --------------------------------------------------------------- #
processing_latency_seconds = Histogram(
    "ledgerflow_processing_latency_seconds",
    "End-to-end pipeline latency per invoice.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)

# --- gauges (rates / eval) ------------------------------------------------- #
auto_approval_rate = Gauge(
    "ledgerflow_auto_approval_rate",
    "Rolling fraction of processed invoices that were auto-approved.",
)
low_confidence_rate = Gauge(
    "ledgerflow_low_confidence_rate",
    "Rolling fraction of processed invoices with any low-confidence required field (drift signal).",
)
field_accuracy = Gauge(
    "ledgerflow_field_accuracy",
    "Overall field extraction accuracy from the most recent eval run.",
)


class _RollingRates:
    """Tiny in-process accumulator so the gauges reflect a live rate, not just the last value."""

    def __init__(self) -> None:
        self.total = 0
        self.auto = 0
        self.low_conf = 0

    def record(self, *, auto_approved: bool, had_low_confidence: bool) -> None:
        self.total += 1
        if auto_approved:
            self.auto += 1
        if had_low_confidence:
            self.low_conf += 1
        if self.total:
            auto_approval_rate.set(self.auto / self.total)
            low_confidence_rate.set(self.low_conf / self.total)


rolling = _RollingRates()
