# Deploying CardSense

Frontend on Vercel, backend on Cloud Run, Firestore as the store. The frontend
is a thin read model over the backend, so the backend goes first.

Everything below is run by you: each step needs your Google or Vercel login.

---

## 1. Backend → Cloud Run

You already have the project and the Firestore database. From `backend/`:

```bash
gcloud config set project project-cc11421f-7c37-404f-a7e
```

Enable what the deploy needs (once):

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com
```

Give the service its own identity, rather than the default one that can touch
everything in the project:

```bash
gcloud iam service-accounts create cardsense-api --display-name="CardSense API"
```

Grant it exactly two things — Firestore, and Vertex AI for the two agents that
use Gemini:

```bash
gcloud projects add-iam-policy-binding project-cc11421f-7c37-404f-a7e --member="serviceAccount:cardsense-api@project-cc11421f-7c37-404f-a7e.iam.gserviceaccount.com" --role="roles/datastore.user"
```

```bash
gcloud projects add-iam-policy-binding project-cc11421f-7c37-404f-a7e --member="serviceAccount:cardsense-api@project-cc11421f-7c37-404f-a7e.iam.gserviceaccount.com" --role="roles/aiplatform.user"
```

Put the Plaid secret in Secret Manager rather than in a deploy command, where it
would sit in your shell history and in the Cloud Run revision description:

```bash
gcloud services enable secretmanager.googleapis.com && printf '%s' 'YOUR_PLAID_SECRET' | gcloud secrets create plaid-secret --data-file=-
```

```bash
gcloud secrets add-iam-policy-binding plaid-secret --member="serviceAccount:cardsense-api@project-cc11421f-7c37-404f-a7e.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

Then deploy. This builds the Dockerfile in `backend/` and runs it:

```bash
gcloud run deploy cardsense-api --source . --region us-central1 --allow-unauthenticated --service-account cardsense-api@project-cc11421f-7c37-404f-a7e.iam.gserviceaccount.com --set-secrets PLAID_SECRET=plaid-secret:latest --set-env-vars DEMO_MODE=false,GOOGLE_CLOUD_PROJECT=project-cc11421f-7c37-404f-a7e,GOOGLE_CLOUD_LOCATION=global,FIRESTORE_DATABASE=all-things-agentic,FINANCE_AGENT_MODEL=gemini-2.5-flash,PLAID_CLIENT_ID=6a79aafc2df7e2000d7d2d7c,PLAID_ENV=sandbox --memory 1Gi --timeout 300 --min-instances 1
```

Two of those flags matter more than they look:

- `--timeout 300` — card intelligence takes about thirty seconds per document,
  and the default request timeout will cut it off.
- `--min-instances 1` — a cold start plus a Gemini call is a long first
  impression. This costs a few dollars a month and is worth it while judging.

Check it:

```bash
curl -s "$(gcloud run services describe cardsense-api --region us-central1 --format='value(status.url)')/health"
```

## 2. Frontend → Vercel

The repo root is not the app, so Vercel needs pointing at it. In the Vercel
dashboard: **Add New → Project**, import `jovann-sim/card-sense`, then set
**Root Directory** to `frontend/web`.

Add one environment variable, for all environments:

```
CARDSENSE_API_URL = https://cardsense-api-XXXX-uc.a.run.app
```

Use the URL the `gcloud run deploy` printed. No trailing slash.

Deploy. If you prefer the CLI, from `frontend/web`:

```bash
npx vercel --prod
```

## 3. Let the frontend talk to the backend

CORS already admits `https://*.vercel.app`, which covers production and every
preview. If you attach a custom domain, add it explicitly:

```bash
gcloud run services update cardsense-api --region us-central1 --update-env-vars CORS_ORIGINS=https://cardsense.app,https://www.cardsense.app
```

## 4. Seed the deployed account

Firestore is shared with your local machine, so the data is already there. If
you want to reset it to the twelve-month demo set:

```bash
curl -X POST "$(gcloud run services describe cardsense-api --region us-central1 --format='value(status.url)')/api/v1/demo/seed-realistic?months=12"
```

```bash
curl -X POST "$(gcloud run services describe cardsense-api --region us-central1 --format='value(status.url)')/api/v1/catalog/seed"
```

---

## About DEMO_MODE

`DEMO_MODE=true` swaps Firestore for an in-memory store with a local JSON file
behind it. That is right for a laptop with no Google credentials, and wrong for
anything deployed: Cloud Run containers are replaced without warning and their
filesystems go with them, so every restart would silently lose the wallet.

Deploy with `DEMO_MODE=false`. The app refuses to start in real mode without
working credentials, which is deliberate — a backend that boots and then
returns empty data is harder to diagnose than one that does not boot.

## What this does not deploy

The browser extension is loaded unpacked from `frontend/extension` and points at
`http://localhost:8080`. To use it against the deployed backend, change `API` at
the top of `popup.js` and add that origin to `host_permissions`.
