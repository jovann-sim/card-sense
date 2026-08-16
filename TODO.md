# CardSense TODO

## Now

- [ ] Review and commit the completed ADK parity, card editing, and dependency updates.
- [ ] Restart the backend with `backend/.venv` and smoke-test card editing, Plaid sync, and an ADK run from the website.

## Next: live checkout recommendations

- [ ] Replace the Chrome extension's fixed recommendation with a backend request.
- [ ] Define a checkout recommendation endpoint that accepts merchant/domain, amount, currency, and optional category.
- [ ] Match the merchant to an MCC or reward category without inventing unsupported precision.
- [ ] Return the best held card, expected reward, comparison against alternatives, and a short explanation.
- [ ] Add extension loading, backend-unavailable, unsupported-merchant, and no-eligible-card states.
- [ ] Ensure the extension never receives Plaid access tokens or other server credentials.
- [ ] Add backend contract tests and extension tests for several merchant categories and reward-rule edge cases.

## Agent quality

- [ ] Add golden evaluation cases for ingestion, card intelligence, strategy, forecast, and advisory outputs.
- [ ] Measure recommendation correctness, unsupported claims, degraded-run frequency, latency, and model cost.
- [ ] Test retry and recovery behavior for individual ADK stage failures.
- [ ] Surface the selected pipeline engine and useful failure details in the activity UI.
- [ ] Add regression cases for minimum spend, reward caps, enrolment requirements, promotions, merchant channels, and statement cycles.
- [ ] Replace placeholder point and mile valuations with sourced, dated assumptions where possible.

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

- [ ] Run `cd backend && .venv/bin/python -m pytest tests -q`.
- [ ] Run `cd frontend/web && npm run lint`.
- [ ] Run `cd frontend/web && npx tsc --noEmit`.
- [ ] Run `cd frontend/web && npm run build`.
- [ ] Confirm documentation and `.env.example` match the deployed configuration.
