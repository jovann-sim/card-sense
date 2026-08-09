# CardSense Backend

Backend for the CardSense frontend and five-agent architecture.

## Stack
- FastAPI API service
- Firestore persistence
- Google Gemini for Card Intelligence + Advisory
- Deterministic Ingestion, Forecast, and Strategy logic
- Optional Plaid sandbox ingestion
- Cloud Run / Cloud Scheduler friendly

The API returns the frontend's existing `Snapshot` contract so the UI can be wired to live data without changing its components.

## Quick start

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8080
```

For local demo mode, set `DEMO_MODE=true`. This uses deterministic seed data and does not require Firestore, Plaid, or Gemini.

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
- `GET /api/v1/runs/{run_id}`
- `POST /api/v1/planned`
- `DELETE /api/v1/planned/{planned_id}`
- `POST /api/v1/goals`
- `POST /api/v1/advice/{advice_id}/resolve`
- `POST /api/v1/cards`
- `GET /api/v1/cards`
- `POST /api/v1/plaid/link-token`
- `POST /api/v1/plaid/exchange-token`
- `POST /api/v1/plaid/sync`
- `POST /api/v1/scheduler/run`

The scheduler endpoint should be protected by a service-to-service secret in production.

## Agent coordination

Agents communicate through persisted state rather than direct agent-to-agent calls. A run writes:

`transactions -> card_rules + forecasts (parallel conceptually) -> strategy_runs -> advice -> snapshots/current`

The implementation exposes this as a single orchestration job, while each agent reads/writes only its own state boundary.

## Plaid transactions

The backend now implements the complete server-side Plaid Transactions flow:

1. `POST /api/v1/plaid/link-token` creates a Plaid Link token.
2. The frontend opens Plaid Link and receives a short-lived `public_token`.
3. `POST /api/v1/plaid/exchange-token` exchanges that token for an `access_token` and stores the credential under `users/{userId}/plaid_items/{itemId}`. The access token is never returned to the browser.
4. `POST /api/v1/plaid/sync` uses `/transactions/sync`, persists added/modified/removed transactions, updates the cursor, rebuilds the existing `ingestion.transactions` contract, and triggers the CardSense orchestrator.

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
