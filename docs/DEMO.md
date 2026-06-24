# Demo — the 2-minute script

The goal of the demo is to make a non-technical finance manager believe the automation
is *safe*. Lead with the cost of the manual process, then show the machine being
careful, not clever.

## Setup (once)

```bash
# full stack
docker compose up --build
# ...or fully local: uvicorn app.main:app  +  npm run dev
python eval/generate_fixtures.py     # if fixtures aren't generated yet
```

Have three tabs ready: **console** (:3000), **Grafana** (:3001), **API docs** (:8000/docs).

## The script

**0:00 — The problem.**
> "This finance team keys about 500 invoices a month by hand. Each one is a few minutes
> and the occasional fat-fingered total costs real money. Here's the same job, automated
> — but automated in a way they can trust."

**0:15 — Drop the batch.**
```bash
python scripts/seed_demo.py
```
Switch to the console. The header fills in live: **30 invoices, ~80% auto-approval,
N synced downstream, dupes prevented**. 

> "Right away, the clean ones — about 80% — extracted, validated against hard business
> rules, and synced to the accounting system with no human at all."

**0:40 — The careful part.** Point at the **Review queue (6)**.
> "It did *not* auto-approve everything. These six it wasn't sure about — and that's the
> whole point. It would rather ask than be confidently wrong."

**0:55 — Open a flagged invoice.** Show the side-by-side: original document on the left,
extracted fields on the right, the **problem field highlighted in amber** with the gate's
plain-English reason at the top (e.g. *"subtotal + tax = 55.00, which does not equal
total 99.00"* or *"low confidence on invoice_number"*).

> "Original on the left, what the model read on the right. It flagged exactly the field
> that's wrong and told me why. I fix the one field…"

Edit the highlighted field → **Approve & sync**.

> "…and on approve it re-runs every validation again. A human can override the model's
> *confidence*, but not the arithmetic — if the totals still didn't add up, it would
> refuse to sync. The record is now written downstream, exactly once."

**1:30 — The reliability story (Grafana).** Switch to the dashboard.
> "Throughput, p95 latency, auto-approval rate, and this one matters: the **drift
> panel**. If a vendor changes their layout or the scans get worse, the low-confidence
> rate climbs *here* before the review queue blows up — so the team gets a heads-up
> instead of a surprise."

**1:50 — The engineering backstop.**
> "And it doesn't rot silently: there's an eval set that runs in CI on every commit. If
> a model or prompt change drops accuracy below the floor, the build goes red."

```bash
python eval/run_eval.py --simulate-regression   # exits non-zero, "EVAL GATE FAILED"
```

**2:00 — Close.**
> "Clean ones automate themselves, the messy ones become a five-second confirmation,
> and nothing money-affecting happens without either passing every rule or a human
> click. That's the difference between a model demo and something finance will actually
> run."

## Things to point out if asked

- **Idempotency:** upload the same file twice → one record (the "dupes prevented"
  counter ticks). Re-syncing never creates a second downstream row.
- **Dead-letter:** kill the provider / force an error → the job retries with backoff,
  then lands in `dead_letter`, visible and requeue-able — never lost.
- **Provider swap:** set `LEDGERFLOW_LLM_PROVIDER=openai` + a key; the gate, validators,
  and UI are untouched.
