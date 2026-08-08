# CardSense — front end

Seven surfaces, all built against placeholder fixtures. Nothing talks to a
backend yet; everything is shaped so wiring it up is a single-file change.

Everything the user enters — cards, planned spending, goals, dismissals — lives
in React state and is gone on reload. That is deliberate for a shell: it demos
correctly and there is no fake persistence layer to unpick when Firestore
arrives.

```
web/         Next.js 16 · TypeScript · Tailwind v4 — the dashboard and its five sibling pages
extension/   Chrome MV3 — the recommend-only checkout popup
```

## Running it

```bash
cd web && npm run dev
```

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
  Declaring a purchase recalculates the projection and, if the category would
  breach a cap, inserts the collision as a new dated warning. That calculation
  is real, in [web/lib/goal.ts](web/lib/goal.ts).
- **Goals** — `/goals`. A track, a target and a date. Pace, projected arrival
  and the shortfall are computed live as the fields change, along with the one
  change that closes the gap.

Recommendations can be marked done or dismissed, which is what feeds
`/history`. Nothing is a dead end: an unset preference, unread rules, and stale
rules each offer the action that resolves them.

## Where the real data goes

**Dashboard and all pages.** Every component reads one object, typed as
`Snapshot` in [web/lib/types.ts](web/lib/types.ts). Replace the export in
[web/lib/mock.ts](web/lib/mock.ts) with a Firestore read returning that same
shape and nothing else changes. Pages are server components, so the read is a
plain `await` — no client fetching, no loading states to build.

**Extension.** The seam is `getVerdict()` in
[extension/popup.js](extension/popup.js). It returns a fixed object today;
point it at the Advisory Agent's endpoint and keep the shape.

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
- **The catalog on `/cards` prices every card against this user's real
  spending, net of annual fee.** A browsable list of cards would be a
  comparison site; a list where every row runs through the strategy agent is
  still the product.
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

## The connect modal is a replay, not a live run

[web/components/ConnectFlow.tsx](web/components/ConnectFlow.tsx) walks the five
agents on a fixed 1.6s cadence — about eight seconds end to end. Real runtime is
roughly 26 seconds, which is too long for a four-minute video, and a live
sandbox call is a bad thing to depend on while recording. When the agents are
wired up, drive the same component from real stage transitions if you want the
honest version, but keep the replay path for the recording.

The `Replay connect` pill in the bottom corner is demo scaffolding. Replace it
with a real empty-state trigger before this is a product.

## Known follow-ups

- Point and mile conversion rates in `mock.ts` are placeholders. The UI says so
  on screen under each track card; replace both the rates and the source line
  before recording.
- The extension popup loads fonts from Google Fonts over the network. Bundle
  the woff2 files into `extension/` so it renders offline.
- `detect.js` is a conservative stub — it reports the merchant and whether the
  page looks like a checkout, and nothing calls it yet.
- The `Retry this run` button on `/activity` is inert until there is an agent
  to retry.
