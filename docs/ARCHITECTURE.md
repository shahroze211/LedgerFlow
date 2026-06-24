# Architecture

LedgerFlow is a linear pipeline with deterministic guardrails wrapped around a single
LLM call. The design bias, stated in priority order, is: **reliability > human-in-the-loop
> observability > clean demo > model quality.** Where a choice trades reliability for
cleverness, reliability wins.

## The pipeline

```
                 ┌──────────────────────────────────────────────┐
  upload /  ──►   │ INGEST   content-hash dedup (P3) ─► enqueue   │
  folder-watch    └───────────────┬──────────────────────────────┘
                                  │ queue (in-process | RQ/Redis)
                 ┌────────────────▼──────────────────────────────┐
                 │ EXTRACT  provider interface (stub|openai|gemini)│
                 │          extract ─► self-check ─► emit          │
                 │          per-field confidence + source spans    │
                 └────────────────┬──────────────────────────────┘
                 ┌────────────────▼──────────────────────────────┐
                 │ VALIDATE (deterministic, P2)                    │
                 │  Σ line items ≈ subtotal · subtotal+tax ≈ total │
                 │  date sane · ISO currency · fuzzy vendor match   │
                 └────────────────┬──────────────────────────────┘
                 ┌────────────────▼──────────────────────────────┐
                 │ GATE (P1)  all required ≥ threshold AND          │
                 │            all validations pass ?                │
                 └──────┬───────────────────────┬─────────────────┘
            auto_approved│                       │needs_review
                 ┌───────▼────────┐     ┌────────▼──────────────────┐
                 │ SYNC (P5)      │     │ REVIEW CONSOLE (Next.js)   │
                 │ idempotent     │◄────│ doc ∥ fields, flag → fix   │
                 │ on invoice id  │     │ approve ─► re-validate ─► sync│
                 └────────────────┘     └───────────────────────────┘

  cross-cutting:  Prometheus → Grafana (P7)  ·  audit log on every transition (P8)
                  retries + dead-letter in the worker (P4)
```

## Swappable seams (the Forward-Deployed thesis)

FDE work is integration work, so every external dependency is one small interface:

| Seam | Interface | Implementations |
|------|-----------|-----------------|
| LLM provider | [`extract/provider.py`](../backend/app/extract/provider.py) `ExtractionProvider` | `stub`, `openai`, `gemini` |
| Storage | SQLAlchemy + cross-dialect `JSON` | SQLite, Postgres |
| Queue | [`queue.py`](../backend/app/queue.py) | in-process, RQ/Redis |
| Sync target | [`sync/base.py`](../backend/app/sync/base.py) `SyncTarget` | mock accounting API (extend to ERP / Sheet) |

Swapping any one is an env var, not a refactor. The gate, validators and audit trail
never change.

## Data model

- **`invoices`** — one row per document, id = `inv_<sha256[:16]>`. Holds raw model
  output, normalized `extracted`, `field_confidence`, `field_sources`,
  `validation_results`, the headline fields, and the gate decision.
- **`line_items`** — children of an invoice, each with its own confidence.
- **`known_vendors`** — the master list fuzzy matching scores against, with a
  downstream account code.
- **`audit_logs`** — append-only, one row per transition / extract / sync / edit (P8).
- **`downstream_records`** — the mock accounting system; PK is the invoice id, which
  is what makes sync idempotent. `write_count` exists purely to *prove* repeats don't
  duplicate.

## The status state machine

`queued → extracting → {auto_approved | needs_review}`, then
`auto_approved/approved → synced`, with `→ dead_letter` reachable from the worker and
`needs_review → approved` from a human. **Illegal transitions raise**
([`models/status.py`](../backend/app/models/status.py)) — a record can never reach
`synced` without passing the gate, which is what makes the audit trail trustworthy.

## Why a stub provider

So the entire system — gate, review queue, idempotent sync, dashboards — is
demonstrable with zero API keys and zero network, and so the eval measures a *real,
deterministic* parse rather than a flaky live call. The stub's confidence is a genuine
function of how cleanly each label/value parsed, so messy fixtures genuinely exercise
the human path. Production swaps the provider; nothing else moves.
