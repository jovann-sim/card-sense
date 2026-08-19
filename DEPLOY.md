# Deploying CardSense

CardSense currently deploys as:

- FastAPI on Google Cloud Run
- Firestore as the non-demo store
- Gemini through Vertex AI
- Plaid Sandbox for bank data
- Next.js on Vercel
- An unpacked Chrome extension configured to call the Cloud Run origin

This is a controlled, synthetic-data hackathon deployment. Cloud Run is public
because neither the dashboard nor the extension has authentication. Do not use
real financial data or treat this as a shared production service.

The current Google Cloud resource names are:

| Resource | Value |
|---|---|
| Project | `project-cc11421f-7c37-404f-a7e` |
| Region | `us-central1` |
| Cloud Run service | `cardsense-api` |
| Runtime service account | `cardsense-api` |
| Firestore database | `all-things-agentic` |
| Plaid secret | `plaid-secret` |
| Internal API secret | `cardsense-internal` |

The commands below assume macOS, Linux, or Cloud Shell and require authenticated
Google Cloud and Vercel CLIs.

## 1. Select the Google Cloud project

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

The named Firestore database must already exist. Local data is shared with this
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

## 2. Create the runtime identity

Create the service account once. Skip the first command if it already exists:

```bash
gcloud iam service-accounts create "$CS_RUNTIME_ACCOUNT" \
  --display-name="CardSense API"
```

Grant only the runtime roles used by the application:

```bash
gcloud projects add-iam-policy-binding "$CS_PROJECT_ID" \
  --member="serviceAccount:${CS_RUNTIME_ACCOUNT}@${CS_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding "$CS_PROJECT_ID" \
  --member="serviceAccount:${CS_RUNTIME_ACCOUNT}@${CS_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

## 3. Create or rotate secrets

Do not put a Plaid secret directly in a command that will be saved in shell
history. For the first secret version:

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

If either secret already exists, add a version instead of trying to create it:

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

Allow the runtime service account to read both secrets:

```bash
gcloud secrets add-iam-policy-binding plaid-secret \
  --member="serviceAccount:${CS_RUNTIME_ACCOUNT}@${CS_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding cardsense-internal \
  --member="serviceAccount:${CS_RUNTIME_ACCOUNT}@${CS_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

If a secret is rotated after deployment, deploy a new Cloud Run revision so its
environment receives the new `latest` version.

## 4. Deploy the backend

Run this from `backend/`, where the Dockerfile and `.dockerignore` live:

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

Why the non-default flags matter:

- `DEMO_MODE=false` selects Firestore. A Cloud Run filesystem is ephemeral, so
  `.localstore.json` is not a deployment store.
- `PIPELINE_ENGINE=adk` is explicit even though ADK is currently the default.
- `--timeout 300` leaves enough time for multi-pass document extraction.
- `--min-instances 1` avoids a cold start during judging, at additional cost.
- `--allow-unauthenticated` is required by the current dashboard and extension,
  but it is also the reason this deployment must contain synthetic data only.

Check the revision and save its origin:

```bash
CS_BACKEND_ORIGIN="$(gcloud run services describe "$CS_SERVICE" \
  --region "$CS_REGION" \
  --format='value(status.url)')"

curl -fsS "$CS_BACKEND_ORIGIN/health"
```

The container installs only `backend/requirements.txt`; test-only dependencies
stay in `requirements-dev.txt`. The image includes `app/`, `adk_agents/`,
`evals/`, and `data/`, which are all required by the runtime and quality page.

## 5. Deploy the frontend

In Vercel, import the current repository:

```text
hcy-05/CardSenseATA
```

Set the project Root Directory to:

```text
frontend/web
```

Add `CARDSENSE_API_URL` to Production and any Preview environments you intend
to use:

```text
CARDSENSE_API_URL=https://cardsense-api-XXXX-uc.a.run.app
```

Use the exact `CS_BACKEND_ORIGIN` printed by Cloud Run, without a trailing
slash. Do not enable `CARDSENSE_USE_MOCK_DATA` in Vercel. Environment changes
apply only to new deployments, so redeploy after adding or changing the value.

Deploy from the Vercel dashboard, or from `frontend/web`:

```bash
cd frontend/web
npx vercel --prod
cd ../..
```

The dashboard reads the backend from the Next.js server and sends browser
mutations through `/api/backend/...`, a same-origin Next.js proxy. It therefore
does not require the viewer's browser to make cross-origin requests to Cloud
Run. The backend still admits Vercel preview origins and unpacked
`chrome-extension://` origins for direct clients.

A custom dashboard domain does not need `CORS_ORIGINS` while the same-origin
proxy remains in use. Set `CORS_ORIGINS` only if a new browser client will call
Cloud Run directly.

## 6. Prepare synthetic demo data

The seed routes are protected by `X-Internal-Secret`. Read the secret into a
shell variable without printing it:

```bash
CS_INTERNAL_SECRET="$(gcloud secrets versions access latest \
  --secret=cardsense-internal)"
```

Seed the descriptive catalogue:

```bash
curl -fsS -X POST "$CS_BACKEND_ORIGIN/api/v1/catalog/seed" \
  -H "X-Internal-Secret: $CS_INTERNAL_SECRET"
```

`catalog/seed` creates unheld reference cards; it does not create the user's
wallet. On a fresh Firestore database, add held cards through the Cards page and
connect/link Plaid Sandbox accounts before expecting attributed reward totals.

Once the wallet exists, this replaces transactions with a deterministic
twelve-month synthetic household history and runs the pipeline:

```bash
curl -fsS -X POST \
  "$CS_BACKEND_ORIGIN/api/v1/demo/seed-realistic?months=12" \
  -H "X-Internal-Secret: $CS_INTERNAL_SECRET"
```

For meaningful captured-reward figures, held cards must already have
`accountId` values. Without linked accounts, the generated transactions remain
unmapped and the ingestion stage correctly reports degraded attribution. This
route is a repeatable transaction seed, not a complete fresh-database bootstrap.

Clear the shell copy of the secret when finished:

```bash
unset CS_INTERNAL_SECRET
```

## 7. Configure the extension

The extension is not deployed by Vercel:

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Choose **Load unpacked** and select `frontend/extension`.
4. Open the CardSense popup and choose **Backend settings**.
5. Enter `CS_BACKEND_ORIGIN`.
6. Accept Chrome's permission request for that backend origin.

No source edit or manifest edit is required. The settings page stores the
origin in `chrome.storage.sync` and requests only that origin through the
manifest's optional host permissions.

Smoke-test:

- a known merchant, which should produce a card and confidence level;
- an unknown merchant, which should decline to guess;
- an unreachable backend, which should show recovery guidance.

## 8. Plaid sync and webhook status

Plaid Link, token exchange, manual sync, scheduled sync, disconnect, and webhook
verification are implemented. The webhook endpoint is:

```text
POST /api/v1/plaid/webhook
```

When Plaid is configured, the endpoint verifies the `Plaid-Verification` ES256
JWT, its issued-at age, and the exact request-body SHA-256 hash.

The current `link/token/create` implementation does not pass a `webhook` URL to
Plaid, and there is no `PLAID_WEBHOOK_URL` setting. A normal deployment
therefore does not automatically register
`$CS_BACKEND_ORIGIN/api/v1/plaid/webhook` for new Items. Manual sync and the
protected scheduler route are the working deployed refresh paths. Do not claim
automatic webhook refresh in a demo until registration is implemented and
existing Items are updated.

## 9. Security boundary

Cloud Run is intentionally public. This means more than public reads:

- anyone with the URL can read the fixed `demo-user` snapshot;
- browser-facing mutations and agent runs are unauthenticated;
- card, goal, planned-spend, advice, and Plaid state can be changed;
- model-backed endpoints can create cost if abused;
- there is no multi-user ownership boundary or rate limiting.

The following operator routes require `X-Internal-Secret`:

- forced agent-quality evaluation;
- Plaid Sandbox seed;
- demo reset and realistic transaction seed;
- catalogue seed;
- scheduler run;
- CSV import.

Webhook signature verification protects only the Plaid webhook route. It does
not authenticate the rest of the API.

Before showing the deployment:

- confirm every transaction and card is synthetic;
- rotate any secret that may have been exposed, add a new Secret Manager
  version, and redeploy;
- verify welcome-bonus dates still tell the intended demo story;
- run the full dashboard and extension journey twice;
- do not connect a real bank account.

## 10. Release checks

Before deployment:

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

After deployment:

```bash
curl -fsS "$CS_BACKEND_ORIGIN/health"
curl -fsS -o /dev/null -w '%{http_code}\n' \
  "$CS_BACKEND_ORIGIN/api/v1/snapshot"
```

Then open the Vercel deployment and verify the dashboard, cards, forecast,
goals, history, activity, write actions, root error boundary, and extension.
