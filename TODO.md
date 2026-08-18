# CardSense TODO

Work in this order. Keep feature work frozen until the submission gate passes.

## Now: submission gate

- [ ] Deploy the backend to Cloud Run and the frontend to Vercel using the documented production configuration.
- [ ] Run the complete deployed journey twice: seed/connect data → analyse → inspect recommendation → open extension → review activity and track record.
- [ ] Point the extension at the deployed backend, accept its scoped host permission, and smoke-test known, unknown, and offline merchant states.
- [ ] Prepare and verify a deterministic seeded-data fallback that does not depend on Plaid or Gemini during the demo.
- [ ] Verify one live Gemini extraction using a reliable issuer PDF and capture the successful result for the demo.
- [ ] Confirm that only synthetic financial data appears in the deployed environment and recording.
- [ ] Rehearse the product story in under four minutes and record the final demo video.
- [ ] Finalise the submission description, architecture visual, disclaimer, and links.

## Release verification

- [ ] Run `cd backend && .venv/bin/python -m evals.run_agent_evals`.
- [x] Run `cd backend && .venv/bin/python -m pytest tests -q` (299 passed on 2026-08-18).
- [x] Run `cd frontend/extension && npm test` (8 passed on 2026-08-18).
- [ ] Run `cd frontend/web && npm run lint`.
- [ ] Run `cd frontend/web && npx tsc --noEmit`.
- [ ] Run `cd frontend/web && npm run build`.
- [ ] Confirm `README.md`, `DEPLOY.md`, component READMEs, and environment examples match the deployed configuration.

## Before lifting the feature freeze

- [ ] Add an end-to-end test covering Plaid sync through snapshot and recommendation publication.
- [ ] Test retry and recovery behavior for each ADK stage failure.
- [ ] Add regression cases for minimum spend, reward caps, enrolment requirements, promotions, merchant channels, and statement cycles.
- [ ] Replace placeholder point and mile valuations with sourced, dated assumptions, starting with KrisFlyer.
- [ ] Run and persist the live Gemini extraction corpus as a release quality gate.

## Next product feature: new-card simulation

- [ ] Simulate each catalogue card as a temporary addition to the current wallet.
- [ ] Calculate its incremental annual reward value using the user's actual spending and existing cap allocation.
- [ ] Subtract annual fees and report net annual value and break-even time.
- [ ] Model welcome bonuses separately, including eligibility uncertainty and minimum-spend attainability.
- [ ] Replace placeholder catalogue `deltaVsWallet` values with deterministic simulation results.
- [ ] Explain which categories create the gain and which conditions were excluded.
- [ ] Add Cards-page verdicts: `Worth adding`, `Marginal`, and `Keep current wallet`.
- [ ] Add regression tests for fees, caps, ties, conditional rules, and benefits-only cards.

## Product backlog

- [ ] Add PDF upload to the Add Card interface.
- [ ] Explain account-mapping and unreadable-terms uncertainty on dashboard recommendations.
- [ ] Validate recommendation outcomes automatically against later transactions and improve the agent track record.
- [ ] Improve welcome-bonus eligibility and minimum-spend progress tracking.
- [ ] Schedule card-terms rechecks and show before/after rule changes.
- [ ] Package and document a production extension build after authentication is available.

## Production readiness after the hackathon

- [ ] Add authentication and remove the fixed `demo-user` assumption.
- [ ] Enforce user ownership for cards, transactions, Plaid Items, runs, and recommendations.
- [ ] Move agent runs to a durable, idempotent job queue.
- [ ] Verify Plaid webhook signatures before processing events.
- [ ] Add structured logs and metrics for Plaid syncs, ADK stages, persistence, and API failures.
- [ ] Store production secrets in a managed secret store and establish rotation procedures.
- [ ] Add rate limits and authorization to mutation and administrative endpoints.
- [ ] Document Firestore backup, recovery, retention, and deletion procedures.
- [ ] Complete privacy, encryption, audit, dependency-security, and threat-model reviews before connecting production accounts.
