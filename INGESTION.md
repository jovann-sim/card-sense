# Ingestion — state and what's next

Baseline: ingestion merge `60df0fe` on `main`, plus the correctness fixes in
the current working tree.

## Working end to end

Plaid sandbox pulls 68 transactions, 48 of them purchases, **100% carrying a
merchant category code**. A card whose last four match a Plaid account mask
links itself, and `captured` is a real number rather than zero.

```bash
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8080
curl -X POST localhost:8080/api/v1/plaid/sandbox/seed -H 'Content-Type: application/json' -d '{"userId":"demo-user"}'
curl -X POST localhost:8080/api/v1/plaid/sync       -H 'Content-Type: application/json' -d '{"userId":"demo-user"}'
```

`sandbox/seed` mints and exchanges a public token in one call, so none of this
needs the Plaid Link UI. It refuses to run outside sandbox.

## What was fixed

| Gap | Resolution |
|---|---|
| `IngestionAgent` never instantiated | It owns the transaction shape; the orchestrator calls it and reports coverage |
| No MCC on transactions | Plaid's `merchant_category_code` where present (44/68), inferred from its taxonomy otherwise (`app/plaid_taxonomy.py`) |
| Transfers counted as spending | 20 of 68 are payments and transfers; marked `isPurchase: false` and skipped by the optimiser |
| No account-to-card link | Auto-linked by mask, credit accounts only, manual endpoint for the rest |
| Plaid coupled to `DEMO_MODE` | Gates on its own credentials, like Gemini |

## Correctness fixes after the initial ingestion merge

- The normal Plaid Link exchange now stores accounts and auto-links cards, not
  only the `sandbox/seed` shortcut.
- Forecast and headline totals exclude transfers, payments and pending rows;
  refunds retain their negative sign and reduce spend.
- Strategy prices each MCC bucket within a display category independently. A
  mixed Travel category no longer prices hotels as flights merely because MCC
  4511 appeared first.
- The ingestion log measures account IDs against wallet links rather than only
  checking whether Plaid supplied an account ID.
- CSV uploads use the same ingestion code, retain MCCs and are idempotent.
- Scheduled runs synchronize Plaid before recalculating when an Item exists.
- The cards page exposes a Plaid credit-account selector for the cases that do
  not auto-link uniquely.

## Known gaps, in priority order

**1. Some sandbox spend lands in "Uncategorised".** Mostly Plaid's
`OTHER_OTHER`. A row with a Plaid-supplied MCC can still match a card rule, but
one without a code has no useful label fallback. Either map more of the
taxonomy or exclude fully unmapped spend rather than assuming a base rate.

**2. Sandbox is US data.** USD amounts, US merchants. Against Singapore cards
the currency and merchant names will look wrong on camera. Consider a seeded
local dataset for the demo.

**3. Inferred MCCs are representative.** A detailed Plaid category is stronger
than a primary-category fallback, but both are currently eligible for matching.
Keep `mccSource` visible when diagnosing a surprising recommendation.
