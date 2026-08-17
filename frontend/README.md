# CardSense — front end

Seven surfaces consume the backend's single `Snapshot` read model through a
shared server-side loader. In local development, the deliberate fixture
fallback can be enabled explicitly while the backend is offline.

Cards, account links, planned spending, goals, and advice resolutions are
persisted through the FastAPI API. Demo mode writes them to
`backend/.localstore.json`; non-demo mode writes them to Firestore. Component
state is only used for forms and optimistic interaction.

```
web/         Next.js 16 · TypeScript · Tailwind v4 — the dashboard and its five sibling pages
extension/   Chrome MV3 — the recommend-only checkout popup
```

## Running it

```bash
cd web && npm run dev
```

For live backend data, start the FastAPI service in a second terminal:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

Then copy `web/.env.local.example` to `web/.env.local`. The default
`CARDSENSE_API_URL=http://localhost:8080` needs no change for local use. The
Next.js server fetches the backend on every request; no browser-side API call
or additional CORS setting is required.

To load the extension: open `chrome://extensions`, turn on Developer mode,
choose **Load unpacked**, and pick the `extension/` folder.

## The pages, and which agent each one answers for

| Route | Question it answers | Agent it showcases |
|---|---|---|
| `/` | What happened, and has your advice been worth taking? | Strategy + Advisory |
| `/forecast` | What is about to happen? | Forecast |
| `/goals` | What am I actually trying to reach? | Strategy |
| `/history` | What did you promise, and what did it actually return? | Advisory |
| `/cards` | What do I hold, and what did you read to decide? | Card Intelligence |
| `/activity` | Is this thing actually running? | All five |
| connect modal | Setup, over the dashboard | Ingestion |

Every agent has a home. That is the answer when a judge asks where agent X
shows up.

## The write path

Three places where the user gives the system something, each placed with the
agent that consumes it rather than buried in a settings page — because two of
them are worth nothing without immediate feedback.

- **Add a card** — `/cards`, and from the catalog's empty-search state. Reads
  the terms document with visible staged extraction, then shows the rules it
  found for the user to correct before they drive anything. Falls back to
  manual rate entry, which is also how a card whose document never parsed gets
  recovered.
- **Planned spending** — `/forecast`, added against the timeline it changes.
  Declaring a purchase persists it and asks the backend Forecast Agent to
  recalculate the projection and any dated cap collision.
- **Goals** — `/goals`. A track, a target and a date. Pace, projected arrival
  and the shortfall are computed live as the fields change, along with the one
  change that closes the gap.

Recommendations can be marked done or dismissed, which is what feeds
`/history`. Nothing is a dead end: an unset preference, unread rules, and stale
rules each offer the action that resolves them.

## Where the real data goes

**Dashboard and all pages.** Every component reads one object, typed as
`Snapshot` in [web/lib/types.ts](web/lib/types.ts). Server components call
[web/lib/api.ts](web/lib/api.ts), which caches `/api/v1/snapshot` for ten
seconds and invalidates that cache immediately after successful mutations. In
development it falls back to [web/lib/mock.ts](web/lib/mock.ts) if the API is
unavailable; production fails visibly instead of showing fake data.

**Extension.** The seam is `getVerdict()` in
[extension/popup.js](extension/popup.js). It sends only the current site URL
and merchant name to `POST /api/v1/advise/merchant`, then renders the winning
held card, runner-up, confidence caveat, and agent trace. Unknown merchants,
unreadable rules, and an unavailable backend produce explicit empty states
instead of a guessed recommendation.

## Decisions worth knowing before you edit

- **Categories are ordered by reward missed, not by amount spent.** The largest
  category is rarely the largest leak.
- **Bar length in the category list is total reward available**; the hatched
  part is what went to the wrong card. The same bar grammar runs full-width in
  the hero, where it sums to the same figures.
- **Every recommendation carries its reasoning chain** under "How this was
  decided", attributed per agent. This is what demonstrates the multi-agent
  architecture to someone watching four minutes of video — keep it legible as
  real data lands.
- **`/history` states the gap between predicted and actual, including when the
  agent was wrong.** Resist the urge to hide the misses; being checkable is the
  whole point of that page.
- **The catalog on `/cards` is currently descriptive.** Held-card state is
  real, but `deltaVsWallet` is not yet produced by a new-card simulation and
  defaults to zero. Do not present catalogue gains as implemented analysis.
- **Dates render in a pinned timezone** ([web/lib/format.ts](web/lib/format.ts)).
  These pages are statically prerendered, so local-time formatting would
  disagree between a UTC build host and a viewer elsewhere and trigger a
  hydration mismatch. Switch to a per-user zone, formatted client-side, when
  accounts are real.
- **The fixtures deliberately include the awkward cases**: a cap reached
  mid-cycle, two cards tied, a sign-up bonus deadline, a terms PDF that failed
  to parse, a stale rate-limited source, an ambiguous merchant, a split-MCC
  transaction, an expired recommendation, and a dismissed one. Keep them —
  they are the states most likely to break the layout, and the ones a judge
  will ask about.
- **The extension never fills or stores a card number**, and says so directly
  above where the user is about to type one.

## The connect modal uses real Plaid and run state

[web/components/ConnectFlow.tsx](web/components/ConnectFlow.tsx) opens Plaid
Link, exchanges the token, synchronizes transactions, and receives the
completed five-agent run produced by that sync. Steps 2 and 3 verify terms and
save the goal. Finishing setup reuses the completed sync run rather than
launching a duplicate analysis. The async run endpoint and polling UI remain as
a fallback for onboarding paths that do not have a completed sync run.

The `Connect accounts` pill is a real trigger, although its fixed position is
still hackathon-oriented UI.

## Known follow-ups

- Some point and mile conversion rates have explicit placeholder fallbacks in
  the backend valuation table. Confirm them before presenting the output as
  financial guidance.
- The extension popup loads fonts from Google Fonts over the network. Bundle
  the woff2 files into `extension/` so it renders offline.
- `detect.js` is a conservative stub — it reports the merchant and whether the
  page looks like a checkout, and nothing calls it yet.
- The `Retry this run` button on `/activity` is inert until there is an agent
  to retry.
