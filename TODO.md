# CardSense TODO

## Now: agent quality

- [x] Add golden evaluation cases for ingestion, card intelligence, strategy, forecast, and advisory outputs.
- [x] Report golden correctness, unsupported claims, degraded/failed-run frequency, latency, and measured recommendation error.
- [x] Record privacy-safe Gemini token usage, run correlation, failures, latency, and configurable estimated cost.
- [ ] Run and persist the live Gemini extraction corpus on a scheduled or release-gated basis.
- [ ] Test retry and recovery behavior for individual ADK stage failures.
- [x] Surface pipeline engine usage, quality gates, latency, and failure/degradation evidence in the activity UI.
- [ ] Add regression cases for minimum spend, reward caps, enrolment requirements, promotions, merchant channels, and statement cycles.
- [ ] Replace placeholder point and mile valuations with sourced, dated assumptions where possible.

## Extension follow-ups

- [ ] Make the backend origin configurable instead of hard-coding `http://localhost:8080`.
- [ ] Add automated popup/content-script tests for known merchants, unknown merchants, unreadable rules, and backend failures.
- [ ] Bundle extension fonts locally so the popup renders without a network font request.
- [ ] Package and document a production extension build after authentication is available.

## Recommendation improvements

- [ ] Calculate catalogue `deltaVsWallet` using a real new-card simulation.
- [ ] Model welcome-bonus eligibility and minimum-spend progress more precisely.
- [ ] Explain when account mapping or unreadable card terms make a recommendation uncertain.
- [ ] Validate recommendation outcomes against later transactions and improve the agent track record.

## Reliability

- [ ] Move background agent runs from in-process FastAPI tasks to a durable job queue.
- [ ] Make queued runs idempotent and safe to retry after worker restarts.
- [ ] Add structured logs and metrics for Plaid syncs, ADK stages, persistence, and API failures.
- [ ] Add end-to-end tests covering Plaid sync through snapshot and recommendation publication.
- [ ] Document backup and recovery for Firestore and local demo data.

## Security and production readiness

- [ ] Add authentication and remove the fixed `demo-user` assumption.
- [ ] Enforce user ownership for cards, transactions, Plaid Items, runs, and recommendations.
- [ ] Verify Plaid webhook signatures before processing events.
- [ ] Store production secrets in a managed secret store and rotate exposed development credentials.
- [ ] Add rate limits and authorization to mutation and administrative endpoints.
- [ ] Review retention, deletion, encryption, and audit requirements for financial data.
- [ ] Complete a threat-model and dependency-security review before connecting production accounts.

## Release verification

- [ ] Run `cd backend && .venv/bin/python -m evals.run_agent_evals`.
- [ ] Run `cd backend && .venv/bin/python -m pytest tests -q`.
- [ ] Run `cd frontend/web && npm run lint`.
- [ ] Run `cd frontend/web && npx tsc --noEmit`.
- [ ] Run `cd frontend/web && npm run build`.
- [ ] Confirm documentation and `.env.example` match the deployed configuration.
