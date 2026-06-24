# LedgerFlow — Invoice Intake Automation

> Build spec for Claude Code. Codename: **LedgerFlow** (rename freely).
> Portfolio piece targeting a **Forward Deployed Engineer** role.
>
> **One-liner:** A finance team manually keys ~500 invoices/month into their
> accounting system. LedgerFlow automates the 80% that are clean, and turns the
> messy 20% into a 5-second human confirmation instead of full manual entry.

---

## 0. Read this first (intent)

This is **not** a model-accuracy demo. It is a **workflow automation** that wraps a
foundation model in enough deterministic guardrails that a non-technical finance
person would trust it with real money.

The thing being graded is **judgment under messy input**, not ML novelty. So the
priorities, in order:

1. **Reliability** — never silently produce a wrong record. Wrong-but-flagged is fine; wrong-but-confident is a failure.
2. **Human-in-the-loop on the hard cases** — confidence gating + a fast review queue.
3. **Observability** — you can see throughput, auto-approval rate, accuracy, and drift on a dashboard.
4. **Clean end-to-end demo** — drop folder in → records sync out → reviewer touches only exceptions.
5. Model quality. (Last. A good prompt + validation beats fine-tuning here.)

If a choice trades reliability for cleverness, choose reliability.

---

## 1. The problem (the story we tell)

Accounts-payable teams receive invoices as PDFs (scanned, photographed, multi-page,
varied vendor layouts, foreign currencies, missing fields) and **manually type** the
key fields into their accounting system. It is slow, error-prone, and the errors cost
real money.

LedgerFlow ingests those invoices, extracts the fields, **validates them against hard
business rules**, auto-approves the confident ones, and routes only the uncertain ones
to a human — who sees the original document side-by-side with the extracted fields and
fixes the one highlighted field in seconds. Approved records sync to a downstream
"accounting system" (a mock REST API / Google Sheet — the integration is the point,
not which system).

**Target outcome to report in the demo:** "~80% auto-approved at >X% field accuracy,
exceptions resolved in <Y seconds each, zero duplicate or malformed records written
downstream."

---

## 2. Non-negotiable principles (the "foolproof" doctrine)

These are **hard requirements**, not nice-to-haves. Every one must be visible in the
code and demonstrable.

| # | Principle | Concrete requirement |
|---|-----------|----------------------|
| P1 | **Confidence-gated autonomy** | Every extracted field carries a confidence score. A configurable threshold splits `auto_approved` vs `needs_review`. No record is ever auto-approved if any required field is below threshold. |
| P2 | **Deterministic validation around the LLM** | The LLM extracts; **hard code verifies.** Line items must sum to the subtotal; subtotal + tax must equal total; dates must parse and be sane; currency must be a known ISO code; vendor must fuzzy-match a known-vendor list. Validation failures force `needs_review` regardless of model confidence. |
| P3 | **Idempotency** | Reprocessing the same invoice (same content hash) never creates a duplicate record. Downstream writes are keyed on a deterministic invoice ID. |
| P4 | **Retries + dead-letter** | Transient failures (LLM timeout, parse error) retry with exponential backoff; after N attempts the job goes to a dead-letter state and is surfaced, never silently dropped. |
| P5 | **No silent auto-send** | Records only sync downstream after passing the gate. Exceptions wait for human approval. Nothing money-affecting happens without either passing all rules or a human click. |
| P6 | **Eval harness in CI** | A labeled fixture set runs on every commit; the build **fails** if extraction accuracy drops below a floor. (This is the MLOps-instinct-applied-to-LLMs differentiator.) |
| P7 | **Observability** | Live metrics: throughput, auto-approval rate, field accuracy on eval set, p95 latency, error rate, and a **drift signal** (spike in low-confidence rate ⇒ input distribution shifted). |
| P8 | **Full audit trail** | Every record stores: original file ref, raw model output, validation results, confidence per field, who/what approved it, and timestamps. Reproducible and explainable. |

> When writing the README, lead with this table. It is the FDE signal.

---

## 3. Architecture

```
                    ┌─────────────────────────────────────────────┐
   invoices/  ──►   │  INGEST                                       │
  (folder or        │  - watch folder / upload endpoint            │
   upload)          │  - content-hash dedup (P3)                    │
                    │  - enqueue job                                │
                    └───────────────┬─────────────────────────────┘
                                    │ (async queue)
                    ┌───────────────▼─────────────────────────────┐
                    │  EXTRACT (agentic)                            │
                    │  - Extractor agent → structured fields + raw │
                    │  - per-field confidence                      │
                    └───────────────┬─────────────────────────────┘
                                    │
                    ┌───────────────▼─────────────────────────────┐
                    │  VALIDATE (deterministic, P2)                 │
                    │  - arithmetic checks (lines→subtotal→total)  │
                    │  - date/currency/format checks               │
                    │  - vendor fuzzy-match against known list     │
                    │  - Validator agent for ambiguous-only cases  │
                    └───────────────┬─────────────────────────────┘
                                    │
                    ┌───────────────▼─────────────────────────────┐
                    │  GATE (P1)                                    │
                    │  all required fields ≥ threshold AND          │
                    │  all validations pass  →  AUTO_APPROVED       │
                    │  else                  →  NEEDS_REVIEW        │
                    └──────┬───────────────────────┬──────────────┘
                           │                        │
              AUTO_APPROVED│                        │ NEEDS_REVIEW
                           ▼                        ▼
              ┌────────────────────┐   ┌───────────────────────────┐
              │ SYNC (P5)          │   │ REVIEW CONSOLE (Next.js)  │
              │ write to mock      │   │ - doc side-by-side w/     │
              │ accounting API /   │◄──│   extracted fields        │
              │ Sheet (idempotent) │   │ - uncertain field flagged │
              └────────────────────┘   │ - 1-click fix + approve   │
                                       └───────────────────────────┘

         Cross-cutting:  Prometheus  →  Grafana  (P7)   |   Postgres audit log (P8)
```

---

## 4. Tech stack (deliberately matches the candidate's resume)

- **Backend:** Python, FastAPI, PostgreSQL.
- **Async/jobs:** RQ or Celery + Redis (RQ is lighter; prefer it unless a reason not to).
- **Agentic extraction:** LangGraph (preferred for explicit state machine) or CrewAI. OpenAI **or** Gemini API behind a provider interface so either works.
- **Frontend:** Next.js review console.
- **Validation:** Pydantic models + plain Python rule functions + `rapidfuzz` for vendor matching.
- **Infra:** Docker + Docker Compose; deploy to AWS (ECS/Fargate or a single EC2 + compose for the demo).
- **Observability:** Prometheus + Grafana (reuse the TimeGuard setup).
- **CI:** GitHub Actions — lint, tests, **eval gate**, Docker build.

Keep every external dependency swappable behind a small interface (LLM provider,
downstream sync target, storage). FDE work is integration work; show that seam.

---

## 5. Repo structure

```
ledgerflow/
├── README.md                 # lead with the problem + the P1–P8 table + demo metrics
├── docker-compose.yml        # api, worker, postgres, redis, prometheus, grafana
├── .github/workflows/ci.yml  # lint, test, EVAL GATE, build
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app + routes
│   │   ├── ingest/           # upload/watch, hashing, dedup, enqueue
│   │   ├── extract/          # agent graph, prompts, provider interface
│   │   ├── validate/         # deterministic rules + fuzzy vendor match
│   │   ├── gate.py           # confidence + validation gating logic
│   │   ├── sync/             # downstream writers (mock API / Sheets) — idempotent
│   │   ├── models/           # Pydantic schemas + SQLAlchemy ORM
│   │   ├── observability/    # Prometheus metrics, drift signal
│   │   └── worker.py         # job consumer, retries, dead-letter
│   └── tests/                # unit + integration
├── eval/
│   ├── fixtures/             # ~30 labeled invoices (real-ish, varied, messy)
│   ├── labels.jsonl          # ground-truth fields per fixture
│   └── run_eval.py           # accuracy report; exit nonzero if below floor (CI hook)
├── frontend/                 # Next.js review console
├── infra/
│   ├── grafana/              # dashboards as JSON
│   └── prometheus/           # scrape config
└── docs/
    ├── ARCHITECTURE.md
    └── DEMO.md               # the 2-min script + the numbers
```

---

## 6. Data model (core)

`invoices` (one row per ingested document):
- `id` (deterministic, derived from content hash) · `content_hash` · `source_ref` (file path/URL)
- `status`: `queued | extracting | needs_review | auto_approved | approved | synced | dead_letter`
- `raw_model_output` (jsonb) · `extracted` (jsonb, normalized) · `field_confidence` (jsonb)
- `validation_results` (jsonb: each rule → pass/fail + message)
- `vendor`, `invoice_number`, `invoice_date`, `currency`, `subtotal`, `tax`, `total`
- `approved_by` (`system` | reviewer id) · `created_at` · `updated_at` · `attempts`

`line_items`: `invoice_id` (fk) · `description` · `qty` · `unit_price` · `amount` · `confidence`

`known_vendors`: `name` · `aliases` (for fuzzy match) · downstream account code.

Every state transition is logged (P8). Status is a strict state machine — invalid
transitions must raise, not pass.

---

## 7. The pipeline, stage by stage

**Ingest.** Accept a folder watch and an upload endpoint. Hash file content → if hash
seen, return existing record (P3). Otherwise create `queued` row, enqueue job.

**Extract.** Agent reads the document and returns a structured object **plus a
per-field confidence**. Prompt must demand strict JSON, refuse to guess missing fields
(emit `null` + low confidence rather than hallucinate), and return raw text spans it
based each field on (for the audit trail and the review UI highlight). Keep the agent
graph explicit: extract → self-check → emit. Store the raw output untouched.

**Validate (deterministic — the spine).** Independent of the model:
- `sum(line_items.amount)` ≈ `subtotal` (tolerance for rounding)
- `subtotal + tax` ≈ `total`
- `invoice_date` parses and is within a sane window (not year 2099, not before 1990)
- `currency` ∈ known ISO set
- `vendor` fuzzy-matches `known_vendors` above a match threshold; else flag
- required fields present
Each check writes a pass/fail + human-readable reason into `validation_results`.

**Gate (P1).** `auto_approved` iff *all* required fields ≥ confidence threshold **and**
*all* validations pass. Otherwise `needs_review`. Thresholds live in config, not magic
numbers in code.

**Sync (P5).** Only `auto_approved` (or human-`approved`) records write downstream.
Writes are idempotent on `invoice.id`. On success → `synced`.

**Review console.** Lists `needs_review` queue. For a selected invoice: render the
original doc on the left, extracted fields on the right, **highlight the field(s) that
failed the gate** (low confidence or failed validation). Reviewer edits, clicks
approve → record re-validates → syncs. Target: a correction is ≤ a few clicks.

---

## 8. Eval harness (P6) — do not skip, this is the differentiator

- `eval/fixtures/` holds ~30 invoices spanning easy → nasty (clean PDF, scanned/rotated,
  photo, multi-page, foreign currency, missing field, weird layout, near-duplicate).
- `eval/labels.jsonl` holds ground-truth fields.
- `eval/run_eval.py` runs extraction over all fixtures and reports **per-field accuracy**,
  overall accuracy, and the **auto-approval rate at the configured threshold**. It exits
  nonzero if overall accuracy < floor (e.g. 0.90) so CI fails on regressions.
- CI runs it on every PR. The README shows the latest numbers.

> Sourcing fixtures: use openly available sample/template invoices and synthetic ones
> you generate; never use real third-party financial data. Vary them deliberately so the
> messy cases actually exercise the gate.

---

## 9. Observability (P7)

Prometheus metrics: `invoices_processed_total`, `auto_approval_rate`,
`field_accuracy` (from eval), `processing_latency_seconds` (histogram → p95),
`extraction_errors_total`, `dead_letter_total`, `low_confidence_rate`.

Grafana dashboard panels: throughput over time, auto-approval rate, p95 latency,
error/dead-letter counts, and a **drift panel** — a sustained rise in `low_confidence_rate`
means inputs drifted (new vendor format, worse scans) and the human queue will grow.
Export dashboards as JSON into `infra/grafana/` so they come up with `docker compose up`.

---

## 10. Build plan (phased — work one milestone at a time, commit per milestone)

> Claude Code: complete and self-verify each milestone before starting the next. Each
> has an acceptance check. Keep PRs/commits scoped to one milestone.

**M0 — Skeleton.** Compose file boots api + worker + postgres + redis. FastAPI health
check green. Pydantic + ORM models + the status state machine in place.
*Accept:* `docker compose up` → `/health` 200; tables created; invalid status transition raises in a unit test.

**M1 — Ingest + dedup + queue.** Upload endpoint + folder watch; content hashing;
dedup; job enqueued; worker picks it up and writes a `queued`→`extracting` transition.
*Accept:* uploading the same file twice yields one record; a job runs end-to-end with a stub extractor.

**M2 — Extraction agent.** Real LLM extraction behind a provider interface (OpenAI/Gemini
swappable), strict-JSON prompt, per-field confidence, raw output + source spans stored.
*Accept:* a real sample invoice produces a populated `extracted` + `field_confidence`; raw output persisted.

**M3 — Deterministic validation + gate.** All rules from §7; gate logic; status routes
to `auto_approved`/`needs_review`; everything logged to `validation_results`.
*Accept:* a clean invoice auto-approves; a tampered one (total ≠ subtotal+tax) is forced to needs_review with a readable reason.

**M4 — Sync (idempotent) + retries/dead-letter.** Downstream writer (mock API or Sheet),
idempotent on id; worker retry/backoff; dead-letter state surfaced.
*Accept:* approved record appears downstream exactly once even if synced twice; a forced failure dead-letters after N attempts, never silently lost.

**M5 — Review console.** Next.js queue + side-by-side doc/fields view, flagged field
highlighted, edit + approve → re-validate → sync.
*Accept:* a needs_review invoice can be corrected and approved from the UI in a few clicks, and then shows as synced.

**M6 — Eval harness + CI gate.** Fixtures + labels + `run_eval.py` + GitHub Actions
running lint, tests, eval gate, docker build.
*Accept:* CI is green; artificially degrading the prompt drops accuracy below floor and turns CI red.

**M7 — Observability.** Prometheus metrics wired; Grafana dashboards provisioned via
compose, including the drift panel.
*Accept:* `docker compose up` brings up Grafana with populated panels after processing a batch.

**M8 — Polish + demo.** `docs/DEMO.md` 2-minute script; README leads with problem +
P1–P8 table + real numbers; seed batch + reset script for clean demos.
*Accept:* a cold `docker compose up` + seed batch reproduces the full story end to end.

---

## 11. Scope discipline (what NOT to do)

- **One vertical** (invoices/AP). No generalizing to "any document."
- **One downstream target** (mock API or one Sheet). The seam matters, not the count.
- **~30 fixtures**, not thousands. Variety over volume.
- **No fine-tuning.** Prompt + validation. ("Chose validation over fine-tuning for
  reliability and speed" is a strong interview answer — say it on purpose.)
- **No auth/multi-tenant/billing.** A single reviewer is enough for the story.
- Don't gold-plate the model; spend the time on the gate, the eval, and the dashboard.

---

## 12. The deliverable that actually lands the interview

The repo is necessary but not sufficient. Ship alongside it:

1. **A 2-minute Loom**: state the manual-process cost → drop a batch in → dashboard
   fills → open one flagged exception → fix in seconds → show it synced → cut to Grafana.
2. **A README that opens with the business problem and the P1–P8 doctrine**, then the
   numbers (auto-approval rate, eval accuracy, p95 latency, zero dupes).
3. One paragraph of **"what I'd do next with a real customer"** (e.g., learn each
   vendor's layout, push the threshold up as trust grows, add their real system as a
   sync target) — this is the forward-deployed mindset on display.

FDE hiring managers are buying *"can this person own a messy customer problem end to
end and make automation people trust."* Every section above exists to prove exactly that.

---

## 13. Stretch goals (only after M0–M8 are solid)

- Email-inbox ingestion (watch a mailbox, not just a folder).
- Per-vendor layout memory (raise confidence for vendors seen before).
- Active-learning loop: human corrections feed back into the fixture set, tightening the eval over time (closes the MLOps loop beautifully).
- A/B the OpenAI vs Gemini provider and chart accuracy/latency/cost in Grafana.
