# CardSense: Project and Deployment Guide

CardSense is a single-user, sandbox-first credit-card reward analyser. It
connects transaction data, reads reward terms for cards in a wallet, compares
actual card use with verified alternatives, forecasts near-term spending, and
shows recommendations with an auditable agent trace.

This document is the deployment-first companion to the main project README. It
combines the current product, architecture, operating constraints, local setup,
and complete deployment procedure in one place.

> CardSense is a working hackathon prototype, not a production financial
> service. Deploy only synthetic data. The current API has no user
> authentication, multi-user isolation, or rate limiting.

## Table of contents

- [Deployment at a glance](#deployment-at-a-glance)
- [Project runtime](#project-runtime)
- [What is implemented](#what-is-implemented)
- [Current deployment values](#current-deployment-values)
- [Deployment procedure](#deployment-procedure)
  - [1. Select the Google Cloud project](#1-select-the-google-cloud-project)
  - [2. Create the runtime identity](#2-create-the-runtime-identity)
  - [3. Create or rotate secrets](#3-create-or-rotate-secrets)
  - [4. Deploy FastAPI to Cloud Run](#4-deploy-fastapi-to-cloud-run)
  - [5. Deploy Next.js to Vercel](#5-deploy-nextjs-to-vercel)
  - [6. Prepare synthetic data](#6-prepare-synthetic-data)
  - [7. Configure the Chrome extension](#7-configure-the-chrome-extension)
  - [8. Understand Plaid webhook status](#8-understand-plaid-webhook-status)
  - [9. Verify the deployment](#9-verify-the-deployment)
  - [10. Deployment security boundary](#10-deployment-security-boundary)
- [Local development](#local-development)
  - [Backend](#backend)
  - [Frontend](#frontend)
  - [Local data and reset behavior](#local-data-and-reset-behavior)
- [Verification before deployment](#verification-before-deployment)
- [Known limitations and next production work](#known-limitations-and-next-production-work)
- [Further documentation](#further-documentation)

## Deployment at a glance

The current hosted shape is:

```text
Browser ──> Vercel / Next.js ──> Cloud Run / FastAPI
                                      │
                  ┌───────────────────┼────────────────────┐
                  │                   │                    │
              Firestore          Vertex AI          Plaid Sandbox
                                      │
Chrome extension ─────────────────────┘
        direct merchant-advice request to Cloud Run
```

| Layer | Current deployment |
|---|---|
| Dashboard | Next.js 16 on Vercel |
| API | FastAPI container on Cloud Run |
| Store | Named Firestore database |
| Agent workflow | Google ADK, with built-in orchestrator fallback |
| Model calls | Gemini through Vertex AI |
| Bank feed | Plaid Sandbox or CSV |
| Extension | Unpacked Chrome MV3 extension |

The backend is deployed first because both the Vercel server and extension need
its Cloud Run origin.

## Project runtime

```text
Plaid Link or CSV
  -> normalised transactions
  -> Ingestion audit
  -> Card Intelligence terms refresh
  -> deterministic Strategy simulation
  -> deterministic Forecast
  -> Advisory wording
  -> validated snapshots/current
  -> Next.js dashboard and merchant advice
```

ADK is the default pipeline engine. The built-in orchestrator remains available
as an immediate fallback through `PIPELINE_ENGINE=orchestrator`. Both paths use
the same stage implementations, persistence, recommendation lifecycle, and
validated `Snapshot` read model.

| Agent | Responsibility | Implementation |
|---|---|---|
| Ingestion | Normalise and audit Plaid/CSV transactions | Deterministic Python |
| Card Intelligence | Extract structured rules from issuer terms | Gemini with deterministic validation |
| Strategy | Calculate captured and alternative reward value | Deterministic Python |
| Forecast | Project 30-day spend and cap collisions | Deterministic Python |
| Advisory | Turn grounded findings into recommendations | Gemini with deterministic fallback/actions |

Gemini never owns arithmetic displayed as money. Card Intelligence fails closed:
unreadable or low-confidence terms are excluded rather than guessed.

## What is implemented

- Plaid Link token creation, token exchange, account storage, cursor sync,
  modified/removed transactions, manual sync, and per-Item disconnect
- Plaid webhook JWT verification against rotating ES256 keys, including token
  freshness and exact request-body hashing
- Automatic unique-mask and manual Plaid account-to-card linking
- CSV ingestion through the canonical transaction contract
- Card terms from URLs, PDFs, uploads, pasted text, or manual rules
- Five-stage run telemetry with `not-run`, `running`, `ok`, and `degraded`
  states
- Run-scoped advice expiry without reopening acted or dismissed recommendations
- Forecasts, goals, planned purchases, history, cards, activity, and connection
  management in the dashboard
- Local JSON persistence in demo mode and Firestore in non-demo mode
- Chrome extension merchant recommendations with conservative abstention
- Golden evaluations across all five agents
- Privacy-safe model telemetry for tokens, latency, outcome, and estimated cost

## Current deployment values

| Resource | Value |
|---|---|
| Google Cloud project | `project-cc11421f-7c37-404f-a7e` |
| Region | `us-central1` |
| Cloud Run service | `cardsense-api` |
| Runtime service account | `cardsense-api` |
| Firestore database | `all-things-agentic` |
| Plaid secret | `plaid-secret` |
| Internal API secret | `cardsense-internal` |
| GitHub repository | `hcy-05/CardSenseATA` |
| Vercel root directory | `frontend/web` |

The commands below assume macOS, Linux, or Cloud Shell and authenticated
Google Cloud and Vercel CLIs.

## Deployment procedure

### 1. Select the Google Cloud project

From the repository root:

```bash
export CS_PROJECT_ID="project-cc11421f-7c37-404f-a7e"
export CS_REGION="us-central1"
export CS_SERVICE="cardsense-api"
export CS_DATABASE="all-things-agentic"
export CS_RUNTIME_ACCOUNT="cardsense-api"

gcloud auth login
gcloud config set project "$CS_PROJECT_ID"
```

The named Firestore database must already exist. Local data is shared with the
deployment only when the local backend also uses `DEMO_MODE=false`, the same
project, and the same `FIRESTORE_DATABASE`. The default local
`DEMO_MODE=true` store in `backend/.localstore.json` is separate.

Enable the required APIs once:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com
```

### 2. Create the runtime identity

Create the runtime service account once. Skip the first command if it already
exists:

```bash
gcloud iam service-accounts create "$CS_RUNTIME_ACCOUNT" \
  --display-name="CardSense API"
```

Grant the application access to Firestore and Vertex AI:

```bash
gcloud projects add-iam-policy-binding "$CS_PROJECT_ID" \
  --member="serviceAccount:${CS_RUNTIME_ACCOUNT}@${CS_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding "$CS_PROJECT_ID" \
  --member="serviceAccount:${CS_RUNTIME_ACCOUNT}@${CS_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

### 3. Create or rotate secrets

Do not type the Plaid secret directly into a command that shell history will
retain.

For first-time creation:

```bash
printf 'Plaid secret: '
read -s CS_PLAID_SECRET
printf '\n'
printf '%s' "$CS_PLAID_SECRET" |
  gcloud secrets create plaid-secret \
    --replication-policy=automatic \
    --data-file=-
unset CS_PLAID_SECRET

CS_INTERNAL_SECRET="$(openssl rand -hex 32)"
printf '%s' "$CS_INTERNAL_SECRET" |
  gcloud secrets create cardsense-internal \
    --replication-policy=automatic \
    --data-file=-
unset CS_INTERNAL_SECRET
```

If the secrets already exist, add versions instead:

```bash
printf 'New Plaid secret: '
read -s CS_PLAID_SECRET
printf '\n'
printf '%s' "$CS_PLAID_SECRET" |
  gcloud secrets versions add plaid-secret --data-file=-
unset CS_PLAID_SECRET

CS_INTERNAL_SECRET="$(openssl rand -hex 32)"
printf '%s' "$CS_INTERNAL_SECRET" |
  gcloud secrets versions add cardsense-internal --data-file=-
unset CS_INTERNAL_SECRET
```

Allow the runtime identity to read both secrets:

```bash
gcloud secrets add-iam-policy-binding plaid-secret \
  --member="serviceAccount:${CS_RUNTIME_ACCOUNT}@${CS_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding cardsense-internal \
  --member="serviceAccount:${CS_RUNTIME_ACCOUNT}@${CS_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

After rotating a secret, deploy a new Cloud Run revision so its environment
receives the new `latest` version.

### 4. Deploy FastAPI to Cloud Run

Run the source deployment from `backend/`, where the Dockerfile and
`.dockerignore` live:

```bash
cd backend

gcloud run deploy "$CS_SERVICE" \
  --source . \
  --region "$CS_REGION" \
  --allow-unauthenticated \
  --service-account "${CS_RUNTIME_ACCOUNT}@${CS_PROJECT_ID}.iam.gserviceaccount.com" \
  --set-secrets "PLAID_SECRET=plaid-secret:latest,INTERNAL_RUN_SECRET=cardsense-internal:latest" \
  --set-env-vars "DEMO_MODE=false,PIPELINE_ENGINE=adk,GOOGLE_CLOUD_PROJECT=${CS_PROJECT_ID},GOOGLE_CLOUD_LOCATION=global,FIRESTORE_DATABASE=${CS_DATABASE},FINANCE_AGENT_MODEL=gemini-2.5-flash,PLAID_CLIENT_ID=6a79aafc2df7e2000d7d2d7c,PLAID_ENV=sandbox" \
  --memory 1Gi \
  --timeout 300 \
  --min-instances 1

cd ..
```

The important choices are:

- `DEMO_MODE=false` selects Firestore. Cloud Run's filesystem is ephemeral.
- `PIPELINE_ENGINE=adk` makes the intended workflow explicit.
- `--timeout 300` leaves time for multi-pass terms extraction.
- `--min-instances 1` avoids a cold start during judging, at additional cost.
- `--allow-unauthenticated` is required by the current dashboard and extension,
  but restricts this deployment to synthetic data.

Save and test the backend origin:

```bash
CS_BACKEND_ORIGIN="$(gcloud run services describe "$CS_SERVICE" \
  --region "$CS_REGION" \
  --format='value(status.url)')"

curl -fsS "$CS_BACKEND_ORIGIN/health"
```

The image installs only `backend/requirements.txt`. It copies `app/`,
`adk_agents/`, `evals/`, and `data/`; all four are required at runtime.

### 5. Deploy Next.js to Vercel

Import this repository in Vercel:

```text
hcy-05/CardSenseATA
```

Set Root Directory to:

```text
frontend/web
```

Add this variable to Production and any Preview environments you will use:

```text
CARDSENSE_API_URL=https://cardsense-api-XXXX-uc.a.run.app
```

Use the exact `CS_BACKEND_ORIGIN` returned by Cloud Run, without a trailing
slash. Leave `CARDSENSE_USE_MOCK_DATA` unset or false. Vercel environment
changes apply only to new deployments, so redeploy after changing the value.

Deploy from the dashboard or CLI:

```bash
cd frontend/web
npx vercel --prod
cd ../..
```

The dashboard performs server-side reads and sends browser mutations through
the same-origin `/api/backend/...` Next.js proxy. A custom dashboard domain does
not require a backend CORS change while this proxy remains in use.

The backend already permits Vercel preview origins and unpacked
`chrome-extension://` origins for direct clients. Set `CORS_ORIGINS` only if a
new browser client will call Cloud Run directly.

### 6. Prepare synthetic data

Read the protected-route secret into a shell variable without printing it:

```bash
CS_INTERNAL_SECRET="$(gcloud secrets versions access latest \
  --secret=cardsense-internal)"
```

Seed the descriptive card catalogue:

```bash
curl -fsS -X POST "$CS_BACKEND_ORIGIN/api/v1/catalog/seed" \
  -H "X-Internal-Secret: $CS_INTERNAL_SECRET"
```

This creates unheld reference cards; it does not create the user's wallet. On a
fresh Firestore database, add held cards through the Cards page and connect or
link Plaid Sandbox accounts before expecting attributed reward totals.

Once the wallet exists, replace transactions with a deterministic twelve-month
synthetic household history:

```bash
curl -fsS -X POST \
  "$CS_BACKEND_ORIGIN/api/v1/demo/seed-realistic?months=12" \
  -H "X-Internal-Secret: $CS_INTERNAL_SECRET"
```

Held cards need `accountId` values for meaningful captured-reward figures.
Without linked accounts, generated transactions are unmapped and Ingestion
correctly reports degraded attribution. This route is a repeatable transaction
seed, not a complete fresh-database bootstrap.

Clear the local shell value:

```bash
unset CS_INTERNAL_SECRET
```

### 7. Configure the Chrome extension

The extension remains an unpacked demo build:

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Select **Load unpacked** and choose `frontend/extension`.
4. Open the popup and select **Backend settings**.
5. Enter the value of `CS_BACKEND_ORIGIN`.
6. Approve Chrome's scoped permission for that origin.

No JavaScript or manifest edit is required. The origin is stored in
`chrome.storage.sync`, and the extension requests only the configured backend
through optional host permissions.

Smoke-test a known merchant, an unknown merchant, and an unreachable backend.

### 8. Understand Plaid webhook status

Plaid Link, token exchange, manual sync, scheduled sync, disconnect, and webhook
verification are implemented. When Plaid is configured,
`POST /api/v1/plaid/webhook` validates:

- the `Plaid-Verification` ES256 JWT;
- the token's issued-at age;
- the exact request-body SHA-256 hash.

The current Link token implementation does not pass a webhook URL to Plaid, and
there is no `PLAID_WEBHOOK_URL` setting. A normal deployment therefore does not
automatically register the Cloud Run webhook for new Items. Manual sync and the
protected scheduler endpoint are the working refresh paths.

Do not claim automatic webhook refresh until Link registration is implemented
and existing Items are updated.

### 9. Verify the deployment

Check the public backend:

```bash
curl -fsS "$CS_BACKEND_ORIGIN/health"
curl -fsS -o /dev/null -w '%{http_code}\n' \
  "$CS_BACKEND_ORIGIN/api/v1/snapshot"
```

Then verify the deployed product journey twice:

1. Open the Vercel dashboard.
2. Connect or seed synthetic data.
3. Run analysis and inspect a recommendation.
4. Check cards, forecast, goals, history, and activity.
5. Exercise a write action and confirm the refreshed snapshot.
6. Open the extension at known and unknown merchants.
7. Confirm the offline/backend-unavailable state.
8. Confirm the root error boundary explains a bad backend URL.

### 10. Deployment security boundary

Cloud Run is intentionally public. Anyone who discovers the origin can:

- read the fixed `demo-user` snapshot;
- invoke browser-facing mutations and agent runs;
- change card, goal, planned-spend, advice, and Plaid state;
- create model cost through ungated model-backed endpoints.

There is no user authentication, ownership boundary, or rate limiting.

These operator routes require `X-Internal-Secret`:

- forced agent-quality evaluation;
- Plaid Sandbox seed;
- demo reset and realistic transaction seed;
- catalogue seed;
- scheduler run;
- CSV import.

Webhook verification protects only the Plaid webhook. It does not authenticate
the rest of the API.

Before presenting the deployment:

- confirm every transaction and card is synthetic;
- rotate exposed secrets, add new Secret Manager versions, and redeploy;
- check date-sensitive welcome-bonus states;
- do not connect a real bank account;
- do not share the deployment as a production financial service.

## Local development

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8080
```

Useful settings:

```env
DEMO_MODE=true
PIPELINE_ENGINE=adk
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=global
FINANCE_AGENT_MODEL=gemini-2.5-flash
GEMINI_ENABLED=
PLAID_CLIENT_ID=
PLAID_SECRET=
PLAID_ENV=sandbox
FIRESTORE_DATABASE=(default)
SNAPSHOT_CACHE_TTL_SECONDS=10
INTERNAL_RUN_SECRET=change-me
```

Plaid, Gemini, and persistence are independently configured. `DEMO_MODE=true`
selects local storage; it does not itself disable Plaid Sandbox or Gemini.

### Frontend

```bash
cd frontend/web
cp .env.local.example .env.local
npm install
npm run dev
```

The frontend expects `CARDSENSE_API_URL=http://localhost:8080`. Development
falls back to fixture data only when
`CARDSENSE_USE_MOCK_DATA=true`; production fails visibly when the backend is
unavailable.

### Local data and reset behavior

- Demo mode persists to `backend/.localstore.json`.
- `DEMO_MODE=false` uses Firestore and Google Application Default Credentials.
- Disconnecting a Plaid Item revokes it remotely, removes only that Item's
  transactions and accounts, unlinks affected cards, and recalculates.
- `POST /api/v1/demo/reset` works only in demo mode with Plaid Sandbox and an
  `X-Internal-Secret`.

## Verification before deployment

Install test-only backend dependencies and run every local gate:

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

As of 2026-08-19, the golden agent evaluation passes 15 cases and 70
assertions, all eight extension tests pass, and web lint, TypeScript checking,
and the production build pass. Refresh any virtual environment created before
webhook verification so `PyJWT[crypto]` is installed.

## Known limitations and next production work

- The entire API still assumes `demo-user`.
- Reward simulation does not enforce every minimum-spend, enrolment,
  merchant/channel, promotion, and statement-cycle condition.
- Some point and mile valuations are explicitly unconfirmed placeholders.
- Catalogue `deltaVsWallet` is not backed by new-card simulation.
- FastAPI background tasks are not a durable, idempotent job queue.
- Browser-facing mutations are unauthenticated and unthrottled.
- Plaid webhook delivery is not registered by Link token creation.
- Secret rotation, backups, retention, privacy, encryption, dependency
  security, and threat modelling need production procedures.

## Further documentation

- [Main project README](README.md)
- [Deployment-only guide](DEPLOY.md)
- [Backend details](backend/README.md)
- [ADK workflow](backend/adk_agents/README.md)
- [Frontend details](frontend/README.md)
- [Extension details](frontend/extension/README.md)
- [Architecture visual](CardSense-Architecture.html)
