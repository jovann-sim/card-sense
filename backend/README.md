# CardSense Backend

Backend for the CardSense frontend and five-agent architecture.

## Stack
- FastAPI API service
- Firestore persistence
- Google Gemini for Card Intelligence + Advisory
- Deterministic Ingestion, Forecast, and Strategy logic
- Optional Plaid sandbox ingestion
- Cloud Run / Cloud Scheduler friendly

The API validates and returns the frontend's existing `Snapshot` contract. The
current frontend intentionally remains fixture-backed; swapping its single
fixture read for `GET /api/v1/snapshot` is a separate frontend change.

## Quick start

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8080
```

For local demo mode, set `DEMO_MODE=true`. Storage stays local and Firestore is
not required. Plaid is independent: supplying `PLAID_CLIENT_ID` and
`PLAID_SECRET` enables Sandbox sync into the local store; leaving them empty
keeps the CSV/seeded-data fallback.

**Gemini is switched on separately from `DEMO_MODE`.** Set `GOOGLE_CLOUD_PROJECT`
and it activates; storage and language model are unrelated concerns, and
coupling them meant you could not read a terms document without also standing
up Plaid. Set `GEMINI_ENABLED=false` to force it off.

In demo mode the store also writes to `.localstore.json` so cards you add
survive a restart. Delete that file to start clean; it is gitignored, and
Firestore takes over entirely when `DEMO_MODE=false`.

The current snapshot has a ten-second per-process read-through cache by
default, configured with `SNAPSHOT_CACHE_TTL_SECONDS`. Agent runs and mutations
replace the cached value when they persist a new snapshot.

## Card intelligence

Reads a card's published terms and returns rules the optimiser can price
directly. Give it a URL — an HTML page or a PDF — or paste the text.

```bash
curl -X POST localhost:8080/api/v1/cards -H 'Content-Type: application/json' -d '{
  "name":"HSBC Revolution","last4":"8842","network":"Visa","track":"miles",
  "termsUrl":"https://issuer.example/terms.pdf"}'
```

PDFs are handed to Gemini whole rather than pre-extracted, so scanned documents
with no text layer still work.

**Every rule carries numbers, not prose:**

| Field | Meaning |
|---|---|
| `valuePerDollar` | Nominal dollars returned per dollar spent. The only field a calculation should use. |
| `rateValue` / `rateUnit` | `4` + `percent`, or `1.4` + `miles_per_dollar` |
| `rewardType` | `cashback`, `points`, `miles` |
| `cap` | **Always spend, in dollars.** A reward cap is divided back through the earn rate. |
| `capValue` / `capType` | The document's own figure and what it limited |
| `minSpend` | Minimum spend in the cycle to qualify |
| `rate` | Display string only. Nothing calculates from it. |

Card-level facts land in `characteristics`: issuer, currency, reward currency,
annual fee, fee waiver spend, minimum income, foreign transaction fee.

**It will not guess.** Given a page whose rates are rendered by JavaScript, it
returns `no_rules_found` rather than reciting the card's rates from training
data, and the card is excluded from every comparison until it parses.

| `parseStatus` | When |
|---|---|
| `parsed` | Rates read, confidence above `EXTRACTION_MIN_CONFIDENCE` |
| `stale` | Fetch, quota or model failure **and** we already hold rules — those stay in use |
| `failed` | Nothing readable, no rates present, or confidence too low |

`failureReason` distinguishes `fetch_failed`, `rate_limited`,
`unsupported_content`, `model_unavailable`, `no_rules_found`, `low_confidence`
and `no_source`.

Other endpoints: `POST /api/v1/cards/{card_id}/recheck` re-reads the stored
terms link; `POST /api/v1/cards/{card_id}/terms` accepts a PDF upload.

## Google Cloud mode

Set `DEMO_MODE=false`, authenticate with Application Default Credentials, and configure:

```env
GOOGLE_CLOUD_PROJECT=your-project
GOOGLE_CLOUD_LOCATION=global
FINANCE_AGENT_MODEL=gemini-2.5-flash
```

The architecture intentionally keeps Plaid access tokens server-side and never exposes them through API responses.

## Endpoints

- `GET /health`
- `GET /api/v1/snapshot`
- `POST /api/v1/runs`
- `POST /api/v1/runs/async`
- `GET /api/v1/runs/{run_id}`
- `POST /api/v1/planned`
- `DELETE /api/v1/planned/{planned_id}`
- `POST /api/v1/goals`
- `DELETE /api/v1/goals`
- `POST /api/v1/advice/{advice_id}/resolve`
- `POST /api/v1/cards`
- `GET /api/v1/cards`
- `POST /api/v1/plaid/link-token`
- `POST /api/v1/plaid/exchange-token`
- `POST /api/v1/plaid/sync`
- `GET /api/v1/plaid/items`
- `DELETE /api/v1/plaid/items/{item_id}`
- `POST /api/v1/demo/reset`
- `POST /api/v1/scheduler/run`

The scheduler endpoint should be protected by a service-to-service secret in production.

## Agent coordination

Agents communicate through persisted state rather than direct agent-to-agent calls. A run writes:

`transactions -> card_rules -> strategy_runs + forecasts -> advice -> snapshots/current`

Forecasts use a zero-filled daily spend rate over up to 90 trailing days and
project a 30-day range from observed variability. Declared plans whose start
date falls inside that horizon are added at the entered amount. Monthly,
quarterly and yearly cap crossings are generated by the backend from actual
card-linked spend; statement-cycle caps remain unverified until statement
boundaries are available. The displayed cost of doing nothing applies the
current deterministic unclaimed-reward rate to projected spend.

Goal and planned-spending mutations use targeted projections instead of full
agent runs: they persist the authoritative input, recompute only the affected
goal or deterministic forecast fields, retain existing advice and activity, and replace the
current snapshot. This keeps interactive writes fast when Firestore is remote.

The projection is the sole owner of the read-model shape. Authoritative user
state lives in subcollections (`transactions`, `planned`, `wallet`,
`forecasts`, `strategy_runs`, `advice`, `agent_runs`, and `snapshots/current`);
card rules are globally keyed by stable card ID. Snapshot responses are checked
against the dashboard contract before they leave the API.

Transactions must include an `accountId` that matches a held card's optional
`accountId` before the service will claim an actual reward amount. Unmapped
transactions are surfaced as degraded rather than assigned a placeholder rate.

## Plaid transactions

The backend now implements the complete server-side Plaid Transactions flow:

1. `POST /api/v1/plaid/link-token` creates a Plaid Link token.
2. The frontend opens Plaid Link and receives a short-lived `public_token`.
3. `POST /api/v1/plaid/exchange-token` exchanges that token for an `access_token` and stores the credential under `users/{userId}/plaid_items/{itemId}`. The access token is never returned to the browser.
4. `POST /api/v1/plaid/sync` uses `/transactions/sync`, persists added/modified/removed transactions, updates the cursor, rebuilds the existing `ingestion.transactions` contract, and triggers the CardSense orchestrator.

### Disconnect and reset

List connected Items without exposing their access tokens:

```bash
curl localhost:8080/api/v1/plaid/items
```

Disconnect one Item. This calls Plaid `/item/remove`, deletes only that Item's
accounts and Plaid transactions, unlinks affected wallet cards, clears stale
advice, and recalculates the snapshot. CSV transactions and other Items remain.
Plaid credentials must still be configured so the access token can be revoked
before its local copy is deleted.

```bash
curl -X DELETE localhost:8080/api/v1/plaid/items/ITEM_ID
```

Return the complete single-user dashboard to zero while preserving the card
catalogue and global card rules. This endpoint works only with
`DEMO_MODE=true` and `PLAID_ENV=sandbox`; it attempts to remove every Plaid
Item first and reports any remote failures while still clearing local demo
state.

```bash
curl -X POST localhost:8080/api/v1/demo/reset \
  -H 'X-Internal-Secret: YOUR_INTERNAL_RUN_SECRET'
```

### Plaid setup

Set these values in `.env`:

```env
DEMO_MODE=false
PLAID_CLIENT_ID=...
PLAID_SECRET=...
PLAID_ENV=sandbox
PLAID_COUNTRY_CODES=US
```

Keep Plaid credentials server-side. Do not put `PLAID_SECRET` or a Plaid `access_token` in the frontend.

For the hackathon, start with Plaid Sandbox. The existing CSV endpoint remains available as a fallback/demo ingestion source.
