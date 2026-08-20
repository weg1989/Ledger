# Ledger — Automated Invoice AP Pipeline

A live, runnable invoice processing system: PDF/image in → tiered extraction
(native text → OCR+LLM → vision LLM) → validation → PO matching → decision
engine → (vendor email or ledger record) out. Every stage of the pipeline is
visible in real time in the UI, and every run is stored in a dashboard.

This app is a thin Flask + vanilla JS wrapper around your original notebook
logic. **`pipeline.py` is your notebook's code, unmodified** (just
reassembled from cells into one importable module). `traced_runner.py`
narrates that same logic stage-by-stage for the live view; `app.py` is the
web server; `static/` is the UI.

## 1. Setup

```bash
cd ledger-invoice-pipeline
python3 -m venv venv && source venv/bin/activate      # optional but recommended
pip install -r requirements.txt
```

You also need two system binaries for OCR/PDF rendering (used by Tier 2/3):

```bash
# macOS
brew install tesseract poppler

# Debian/Ubuntu
sudo apt-get install tesseract-ocr poppler-utils
```

## 2. Run it

```bash
# Offline mode (no API key) — Tier 2 falls back to regex-on-OCR-text,
# Tier 3 is skipped since there's no offline substitute for vision reasoning.
python3 app.py

# Live mode — Tier 2/3 make real gpt-4o-mini calls
export OPENAI_API_KEY=sk-...
python3 app.py
```

Open **http://127.0.0.1:5050**. The top-right badge tells you which mode
you're in.

If you ever want to regenerate the bundled sample invoices (or add more
edge cases), run `python3 sample_gen.py` — it writes into `samples/`.

## 3. Using it

**Live Run tab**
- Pick one of the 7 bundled scenarios (1 happy path + 6 edge cases), or
  drag/drop your own PDF or image.
- Click **Run pipeline**. The stage ledger on the left lights up live as
  each stage runs — including stages the pipeline *skipped* and why (e.g.
  "Tier 1 confidence 91 ≥ threshold — stopping, no OCR/LLM cost incurred").
  Click any stage to see its reasoning/data in the detail pane on the right.
- When a decision lands, a stamp animates onto the invoice preview
  (APPROVED / HOLD / REJECTED / AWAITING VENDOR).
- If the outcome is **AWAITING_VENDOR_INFO**, a correspondence panel
  appears showing the auto-drafted outbound email. You can type in the
  vendor's "reply" (e.g. supply the missing PO number) and hit **Send
  reply & reprocess** — this runs the corrected data back through the exact
  same validate → match → decide pipeline live, so you can watch a case
  resolve end-to-end without restarting.
- The **procurement system state** panel at the bottom shows the PO ledger
  and any open correspondence threads — this is "the system of record" the
  pipeline is reasoning against, and it updates as you run invoices, so you
  can demonstrate things like split-PO balances draining or duplicates
  being caught against history.

**Dashboard tab**
- Aggregate stats (auto-approval rate, avg confidence, avg latency) and a
  full run history table. Click any row to replay that run's full reasoning
  trail without re-running it.

## 4. The 7 bundled scenarios

| File | What it tests |
|---|---|
| `clean_invoice.pdf` | Happy path — stops at Tier 1, exact PO match, auto-approved |
| `scanned_invoice.png` | No text layer — forces Tier 2 (OCR+LLM) |
| `split_po_invoice.pdf` | Second installment against a partially-billed PO |
| `duplicate_invoice.pdf` | Resubmission of an already-processed invoice |
| `missing_fields_invoice.pdf` | No invoice number / total — every tier tried before honest hold |
| `embedded_tax_invoice.pdf` | Tax stated as already included in total, not additive |
| `no_po_invoice.pdf` | Everything present except a PO number → vendor correspondence loop |

Run them in this order once (clean → duplicate) to see the duplicate check
work against real history rather than a canned example — the app keeps
state across runs, just like a real AP system would.

## 5. Recording the 5-minute demo video

Suggested beats (aim for ~5 min total):

1. **(30s) What this is.** One sentence on the problem (invoices arrive in
   wildly inconsistent formats; this pipeline extracts, validates, matches
   against POs, and decides — escalating through cheaper tiers only when it
   has to) and a glance at the UI layout.
2. **(90s) Happy path, live.** Run `clean_invoice.pdf`. Narrate: it stays at
   Tier 1 (no OCR/LLM cost), point out the confidence score, the exact PO
   match, and the AUTO_APPROVE stamp. Click into 2–3 stages to show the
   reasoning text, not just the verdict.
3. **(90s) One structural edge case.** Run `scanned_invoice.png` — same
   invoice, but forced through OCR+LLM, to show the escalation gate actually
   escalating. Then run `duplicate_invoice.pdf` to show a same-session
   duplicate getting caught against the ledger.
4. **(90s) The interesting one.** Run `no_po_invoice.pdf`, show the
   AWAITING_VENDOR_INFO stamp and the auto-drafted email, then submit a
   simulated vendor reply live and watch it reprocess to AUTO_APPROVE.
5. **(30s) Wrap.** Flip to the Dashboard tab, show the run history and
   stats, mention what you'd add with more time (real inbound-email
   webhook instead of a simulated reply, currency conversion, a second
   human-in-the-loop UI for the HOLD_FOR_REVIEW queue).

No slides, no editing needed — the live stage ledger and the stamp are
doing the "explaining itself" work for you.

## 6. Architecture notes (for the follow-up interview)

- **Tiered extraction, cheapest first**: Tier 1 (native PDF text via
  `pdfplumber`) → Tier 2 (Tesseract OCR + `gpt-4o-mini` text) → Tier 3
  (`gpt-4o-mini` vision on a page image). Each tier is only invoked if the
  previous one didn't clear a confidence threshold — visible live via the
  escalation-gate stages.
- **Nothing is discarded across tiers** — `merge_extractions` fills gaps
  field-by-field rather than letting a later, noisier tier overwrite a
  confident earlier field.
- **Decisioning is a deterministic rules engine**, not an LLM call — every
  branch is auditable and logged to a reasoning trail (`decision.reasoning_trail`)
  that's shown verbatim in the UI, not summarized.
- **Vendor correspondence, not a black-box review queue**: instead of just
  flagging "needs review", the system drafts a specific, referenceable email
  and — once a reply comes in — re-runs the *same* validate → match → decide
  pipeline on the corrected data, so a resolved case is held to the same
  bar as everything else.
- **Live view vs. dashboard are two different windows onto the same result
  object** — the SSE-streamed stage events during a run, and the same JSON
  replayed from SQLite afterward, so there's exactly one source of truth
  per run.
