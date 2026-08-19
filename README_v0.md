# CardSense

CardSense is a single-user, sandbox-first credit-card reward analyser. It
connects transaction data, reads reward terms for cards in a wallet, compares
actual card use with verified alternatives, forecasts near-term spending, and
shows recommendations with an agent trace.

The current repository is a working hackathon prototype, not a production
financial service. Plaid Sandbox and CSV ingestion are functional, the web
dashboard and Chrome extension use the live backend, and all five agents have
deterministic golden quality gates. Authentication, rate limiting, durable job
execution, and exact handling of every reward condition remain future work.

## Current runtime

```text
Plaid Link or CSV
  -> normalised transactions
  -> Ingestion audit
  -> Card Intelligence terms refresh
  -> deterministic Strategy simulation
  -> deterministic Forecast
  -> Advisory wording
  -> validated snapshots/current
  -> Next.js dashboard
```

The default engine is the ADK workflow. All five stages persist the same read
model and recommendation lifecycle as the built-in orchestrator, which remains
available as an explicit fallback with `PIPELINE_ENGINE=orchestrator`.

Agents coordinate through persisted collections rather than calling each
other directly:

| Agent | Responsibility | Implementation |
|---|---|---|
| Ingestion | Normalise and audit Plaid/CSV transactions | Deterministic Python |
| Card Intelligence | Extract structured rules from issuer terms | Gemini with deterministic validation |
| Simulation & Strategy | Calculate captured and alternative reward value | Deterministic Python |
| Forecast | Project 30-day spend and cap collisions | Deterministic Python |
| Advisory | Turn findings into recommendations | Gemini with deterministic fallback/actions |

Gemini never owns arithmetic displayed as money. Card Intelligence also fails
closed: unreadable or low-confidence terms are excluded instead of guessed.

## What works

- Plaid Link token creation, token exchange, account storage, cursor sync,
  modified/removed transactions, verified webhooks, manual sync, and per-Item
  disconnect
- Plaid webhook JWT verification against Plaid's rotating ES256 keys, including
  issued-at freshness and an exact request-body hash check
- Plaid credit-account to wallet-card linking, automatic only for a unique
  credit-account mask match, with manual linking available
- CSV import through the same canonical transaction contract
- Card terms from URLs, PDFs, uploads, pasted text, or manually entered rules
- Five-stage run logging with `not-run`, `running`, `ok`, and `degraded` states
- Run-scoped recommendations that expire when a later strategy run no longer
  supports them, without reopening acted or dismissed advice
- Forecasts, goals, planned purchases, recommendations, history, cards, Plaid
  connection management, and truthful empty states in the dashboard
- Local JSON persistence in demo mode and Firestore in non-demo mode
- Typed and validated `Snapshot` contract shared by FastAPI and Next.js
- Sandbox-only full reset and scoped Plaid disconnect
- Chrome extension recommendations from the live merchant advisory endpoint,
  with conservative merchant matching and explicit unavailable/unknown states
- Auditable golden evaluations for all five agents, with exact financial,
  grounding, abstention, and recovery quality gates
- Activity-page quality reporting for golden results, real run degradation and
  failures, per-agent latency, engine usage, and measured recommendation error
- Privacy-safe Gemini telemetry linked to agent/run IDs, including input,
  output and thinking tokens, call outcomes, latency, and estimated USD cost

## Important limitations

- All API operations use the fixed `demo-user`; there is no authentication or
  multi-user isolation.
- Reward simulation does not yet enforce every minimum-spend, enrolment,
  merchant/channel, promotional, and statement-cycle condition precisely.
- Reward-unit valuations include stated assumptions and fallbacks.
- ADK is the default pipeline engine; the deterministic orchestrator remains
  available as a fallback through `PIPELINE_ENGINE=orchestrator`.
- Catalogue `deltaVsWallet` values are not yet calculated by a new-card
  simulation.
- FastAPI background tasks are not a durable production job queue.
- Browser-facing mutations are not authenticated or rate-limited; only
  operator-only reset, seed, import, scheduler, and evaluation routes require
  `X-Internal-Secret`.
- Production secret rotation, backup/recovery, privacy, and threat-model work is
  not complete.

Do not connect production financial accounts or expose this API to multiple
people in its current form.

## Local setup

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8080
```

Frontend:

```bash
cd frontend/web
cp .env.local.example .env.local
npm install
npm run dev
```

The frontend expects `CARDSENSE_API_URL=http://localhost:8080`. Mock data is
used only in development when `CARDSENSE_USE_MOCK_DATA=true`; production fails
visibly if the backend is unavailable.

Useful backend settings:

```env
DEMO_MODE=true
PLAID_CLIENT_ID=...
PLAID_SECRET=...
PLAID_ENV=sandbox
GOOGLE_CLOUD_PROJECT=...
GEMINI_ENABLED=true
GEMINI_INPUT_USD_PER_MILLION=0.15
GEMINI_OUTPUT_USD_PER_MILLION=0.60
GEMINI_THINKING_USD_PER_MILLION=3.50
PIPELINE_ENGINE=adk
SNAPSHOT_CACHE_TTL_SECONDS=10
INTERNAL_RUN_SECRET=replace-this
```

Plaid, Gemini, and storage are independently configured. `DEMO_MODE=true`
selects local storage; it does not disable Plaid Sandbox or Gemini.

## Data and reset behavior

- Demo mode persists to `backend/.localstore.json` by default.
- `DEMO_MODE=false` uses Firestore and requires Google Application Default
  Credentials.
- Disconnecting a Plaid Item revokes it remotely, removes only that Item's
  transactions/accounts, unlinks affected cards, and recalculates.
- `POST /api/v1/demo/reset` is allowed only in demo mode with Plaid Sandbox and
  requires `X-Internal-Secret`. It clears the single user's operational data
  while preserving the catalogue and global card rules.

## Verification

Install the backend's test-only dependencies before running the suite:

```bash
cd backend
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
.venv/bin/python -m evals.run_agent_evals

cd ../frontend/extension
npm test

cd ../web
npm run lint
npx tsc --noEmit
npm run build
```

As of 2026-08-19, the golden agent evaluation (15 cases, 70 assertions),
extension tests (8 tests), web lint, TypeScript check, and production build all
pass. A virtual environment created before webhook verification was added must
be refreshed from `requirements-dev.txt` so that `PyJWT` is installed before
the backend suite can be collected.

See [backend/README.md](backend/README.md),
[frontend/README.md](frontend/README.md), and
[CardSense-Architecture.html](CardSense-Architecture.html) for implementation
details and explicit current/future boundaries.
