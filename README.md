# LedgerFlow — Invoice Intake Automation

A finance team keys ~500 invoices a month into their accounting system by hand. It's
slow, it's error-prone, and the errors cost real money. **LedgerFlow automates the
~80% of invoices that are clean, and turns the messy ~20% into a 5-second human
confirmation** instead of full manual entry.

This is not a model-accuracy demo. It's a **workflow automation that wraps a
foundation model in enough deterministic guardrails that a non-technical finance
person would trust it with real money.** The thing on display is judgment under messy
input: a confidence gate, hard-coded validation around the LLM, idempotent writes,
retries with a dead-letter, an eval gate in CI, and an observability story — all so
that a wrong record is *never produced silently*.

---

## The doctrine (read this first — it's the whole point)

| #  | Principle | How it shows up in this repo |
|----|-----------|------------------------------|
| **P1** | **Confidence-gated autonomy** | Every field carries a confidence; [`gate.py`](backend/app/gate.py) auto-approves **iff** every required field clears the threshold **and** every validation passes. Thresholds live in [`config.py`](backend/app/config.py), never as magic numbers. |
| **P2** | **Deterministic validation around the LLM** | [`validate/rules.py`](backend/app/validate/rules.py) hard-codes the checks: line items → subtotal, subtotal + tax → total, date sanity, ISO currency, fuzzy vendor match. A validation failure forces `needs_review` *regardless of model confidence*. |
| **P3** | **Idempotency** | The invoice id is derived from a content hash ([`ingest/hashing.py`](backend/app/ingest/hashing.py)). Re-ingesting the same bytes returns the existing record; downstream writes upsert on that id, so a double-sync never duplicates. |
| **P4** | **Retries + dead-letter** | [`worker.py`](backend/app/worker.py) retries transient failures with exponential backoff, then routes to `dead_letter` — surfaced in the UI, never dropped. |
| **P5** | **No silent auto-send** | Only `auto_approved` / human-`approved` records sync ([`pipeline.sync_invoice`](backend/app/pipeline.py)). A reviewer can override *confidence*, but **not** the arithmetic — approval is refused if validations still fail. |
| **P6** | **Eval harness in CI** | [`eval/run_eval.py`](eval/run_eval.py) runs labelled fixtures on every commit and **fails the build** if accuracy drops below the floor. A simulated regression is asserted to turn CI red. |
| **P7** | **Observability** | Prometheus metrics + a provisioned Grafana dashboard, including a **drift panel** (a sustained rise in low-confidence rate ⇒ inputs shifted ⇒ the human queue will grow). |
| **P8** | **Full audit trail** | Every state transition goes through [`audit.transition`](backend/app/audit.py); raw model output, per-field confidence, source spans, and validation results are all persisted. The status machine *raises* on illegal transitions. |

---

## Numbers (from the bundled eval set, stub provider)

Run `python eval/run_eval.py`:

```
fixtures:              30
overall accuracy:      100.0%
auto-approval rate:     80.0%
gate routing accuracy: 100.0%   (gate sends exactly the right invoices to humans)
floor: 90.0% -> PASS
```

- **80% auto-approved** — the clean majority never touches a human.
- **100% field accuracy** on the fixture set — and when accuracy is artificially
  degraded, `run_eval.py --simulate-regression` drops it to ~71% and **exits non-zero**.
- **Zero duplicate or malformed downstream records** — proven by `test_pipeline.py`.

> The stub provider is a deterministic, offline stand-in for a real vision/LLM model:
> it parses rendered invoice text with fuzzy label matching and *realistic failure
> modes* (garbled labels → low confidence, missing fields → null, tampered totals →
> caught by arithmetic). Swap in OpenAI or Gemini with one env var and the same gate,
> validators and sync run unchanged — that swappable seam is the Forward-Deployed point.

---

## Quickstart

### Option A — fully local, zero dependencies (recommended first run)

No Docker, no Postgres, no Redis, no API keys. SQLite + in-process queue + stub provider.

```bash
# 1. backend
cd backend
python -m venv .venv && .venv/Scripts/activate        # Windows
# source .venv/bin/activate                            # macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload                          # http://localhost:8000/docs

# 2. frontend (separate terminal)
cd frontend
npm install
npm run dev                                            # http://localhost:3000

# 3. seed a demo batch (separate terminal, from repo root)
python eval/generate_fixtures.py                       # writes eval/fixtures + labels
python scripts/seed_demo.py                            # uploads them to the API
```

Open **http://localhost:3000**: the dashboard fills, ~24 invoices auto-approve and
sync, and 6 land in the review queue. Open a flagged one, fix the highlighted field,
click **Approve & sync**.

### Option B — the full "production-shaped" stack

Postgres + Redis + an RQ worker + Prometheus + Grafana, all via compose:

```bash
docker compose up --build
python scripts/seed_demo.py
```

- Review console → http://localhost:3000
- API docs → http://localhost:8000/docs
- Prometheus → http://localhost:9090
- Grafana (anonymous admin) → http://localhost:3001 → dashboard **“LedgerFlow — Invoice Intake”**

Plug in a real model by setting `LEDGERFLOW_LLM_PROVIDER=openai` and
`LEDGERFLOW_OPENAI_API_KEY=...` (or the `gemini` equivalents) in the environment.

---

## How a single invoice flows

```
ingest ─► extract ─► validate ─► gate ─┬─► auto_approved ─► sync ─► synced
(hash/    (provider   (hard-coded       │
 dedup)    interface)  rules + fuzzy)    └─► needs_review ─► [human edits] ─► approved ─► sync ─► synced
                                              │
 transient failure ─► retry/backoff ─► dead_letter (surfaced, requeue-able)
```

Every box is a swappable seam: **provider** (stub / OpenAI / Gemini), **storage**
(SQLite / Postgres), **queue** (in-process / Redis-RQ), **sync target** (mock
accounting API / your ERP). See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Tests & the eval gate

```bash
cd backend && pytest -q          # state machine, dedup, gate routing, idempotent sync, dead-letter
python eval/run_eval.py          # accuracy + auto-approval rate; exits non-zero below floor
ruff check backend               # lint
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs lint → tests → the
eval gate → a regression-guard job (asserts a simulated regression fails) → docker build.

---

## What I'd do next with a real customer

Forward-deployed, the first weeks aren't about the model — they're about earning the
right to raise the threshold:

1. **Learn each vendor's layout.** Cache per-vendor field positions and priors so
   repeat vendors extract with higher confidence and auto-approve more often.
2. **Ratchet the threshold up as trust grows.** Start conservative (lots of review),
   watch the eval + the reviewer override rate, and raise `confidence_threshold` only
   when the data earns it.
3. **Make their system the sync target.** The mock API is one file behind an
   interface; swap in NetSuite / QuickBooks / a Sheet without touching the gate.
4. **Close the loop.** Feed reviewer corrections back into the fixture set so the eval
   tightens over time and drift gets caught before it reaches the queue.

That progression — conservative autonomy that compounds into trust — is the job.

---

## Repo map

```
backend/   FastAPI app: ingest, extract (provider interface), validate, gate, sync, worker, observability
frontend/  Next.js review console (queue, side-by-side doc/fields, edit + approve)
eval/      fixture generator, labels, run_eval.py (the CI accuracy gate)
infra/     prometheus scrape config + provisioned grafana dashboards
scripts/   seed_demo.py, reset_local.py
docs/      ARCHITECTURE.md, DEMO.md
```
