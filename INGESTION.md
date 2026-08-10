# Ingestion — state and what's next

Branch: `feat/ingestion` · 2 commits on top of `main`

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

## Known gaps, in priority order

**1. Some rules do not match despite correct MCCs.** A sandbox run put $1,500
of air travel (MCC 4511) on the base 1% rather than a card's 3% travel rule.
Worth tracing `strategy._matches()` against a real extracted rule — the MCC is
right on both sides, so the fault is in matching, and it directly understates
the gap the whole product is about.

**2. $7,112 of sandbox spend lands in "Uncategorised".** Mostly Plaid's
`OTHER_OTHER`. Those transactions can only match by category name, and
"Uncategorised" matches nothing, so they all fall to the base rate. Either map
more of the taxonomy or treat unmapped spend as excluded rather than base-rate.

**3. Sandbox is US data.** USD amounts, US merchants. Against Singapore cards
the currency and merchant names will look wrong on camera. Consider a seeded
local dataset for the demo.

**4. No UI for linking.** `GET /api/v1/plaid/accounts` lists accounts and which
card each is attached to, and `POST /api/v1/cards/{id}/link-account` attaches
one, but nothing in the interface calls either. Only needed when a mask and a
last four genuinely differ.

**5. Nothing schedules a sync.** `/api/v1/plaid/sync` is manual;
`/api/v1/scheduler/run` exists but does not sync Plaid.
