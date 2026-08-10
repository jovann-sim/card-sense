# Card intelligence — handover

Branch: `feat/card-intelligence` · 6 commits

The card intelligence agent now reads a real terms document — a URL or a PDF —
and returns reward rules the strategy agent can price without parsing prose.
This note covers what changed, how to run it, how to test it, and what is left.

---

## 1. Why this needed doing

The agent required `termsText` to already be a string and ignored `termsUrl`
entirely. So a user pasting the link the form asks for got `failed` without a
request ever being made. There was no PDF support, JSON was requested inside a
prompt and salvaged from whatever came back, and every failure — network,
quota, unreadable document, no rates present — collapsed into one identical
fallback.

Downstream, `strategy.py` worked out what a card returned by running a regex
over the string `"4% cash back"`.

---

## 2. What changed

| Commit | What it does |
|---|---|
| `9923005` | Fetches URLs and PDFs, response-schema extraction, priced rules, real failure taxonomy |
| `8ad0f0b` | Add-a-card calls the agent instead of posting hardcoded rules |
| `07ba8a0` | Per-programme valuations, Singapore dollars as base currency |
| `565d691` | Conditional rewards: scope, currency choice, MCC codes |
| `1ab28f1` | Eval corpus of 10 hard cards, two-pass extraction, benefits, MCC backfill |

### The important part for you

**Every rule now carries numbers, not prose.** `valuePerDollar` is nominal
currency returned per dollar spent, priced through the card's own programme at
extraction time. Nothing downstream should ever parse a rate string again.

```
valuePerDollar    0.0798      ← the only field a calculation should use
rateValue/Unit    4.2 + miles_per_dollar
rewardType        cashback | points | miles
rewardCurrency    "KrisFlyer miles"
rewardUnitValue   0.019       ← what one unit is assumed to be worth
cap               900.00      ← ALWAYS spend, in the card's currency
capValue/capType  3600 + "reward"   ← what the document actually said
mccCodes          ["5812","5813","3000-3299"]
merchants         ["Cold Storage","Giant"]   ← a vendor rate, not a category rate
channels          online | in_store | contactless | foreign_currency
exclusions        what the document rules out
conditions[]      minimum_spend | enrolment | category_selection |
                  banking_relationship | new_customer | promotional_period
requiresSelection + selectableCategories
rewards[]         every currency it can pay in; >1 means the holder chooses
```

`cap` is worth reading twice. Issuers cap either the spend that earns the bonus
rate or the reward itself. A reward cap is now divided back through the earn
rate before it is stored, so `cap` always means spend and the optimiser can
allocate against it directly. The document's own figure stays in `capValue`.

### Changes inside strategy.py

- `_rate()` uses `valuePerDollar` when present; the old regex remains only as a
  fallback for rules recorded before it existed.
- `_matches()` matches on **MCC first**, label second. `4121` is unambiguous
  where "Travel" and "Transport" read alike. Ranges like `3000-3299` work.
- `unmet_conditions()` returns qualifiers that cannot be verified from
  transactions. Categories priced off such a rule get flagged
  `conditional-rate` rather than counted as though the user had already
  nominated the category or opened the linked account.
- `VALUATIONS` now re-exports from `app/valuations.py`; there is one table.

---

## 3. Getting it running

**macOS ships Python 3.9 and this will not run on it.** The code uses
`str | None` inside pydantic models, which raises `TypeError` before the server
starts. You need 3.10+.

```bash
brew install python@3.12
cd backend && /opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate && pip install -r requirements.txt
```

### Gemini access

You need your own Google Cloud project, or to be added to the existing one.

```bash
brew install --cask google-cloud-sdk
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com
```

Billing must be enabled on the project. Gemini Flash costs a fraction of a cent
per document.

Then `cp .env.example .env` and set `GOOGLE_CLOUD_PROJECT`. **Leave
`DEMO_MODE=true`** — Gemini is switched on separately now, by having a project
configured, so you do not need Plaid or Firestore to work on extraction.

### Run it

Two terminals, both stay open:

```bash
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8080
```

```bash
cd CardSenseFrontend/web && npm run dev
```

The frontend needs `CardSenseFrontend/web/.env.local`:

```
CARDSENSE_API_URL=http://localhost:8080
CARDSENSE_USE_MOCK_DATA=false
```

Cards persist to `backend/.localstore.json` between restarts. Delete it to
start clean. It is gitignored, and Firestore takes over when `DEMO_MODE=false`.

---

## 4. Testing it

### Tests first

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/ -q
```

57 tests, no network and no Gemini — a fake runtime stands in.

### Through the UI

`http://localhost:3000/cards` → **+ Add a card**. Paste a link to an issuer's
terms **PDF**, pick the network and what the card earns, then **Read the
terms**. You get back what the agent actually read, with its confidence and
source, for correction before anything is saved.

### Through the API

```bash
curl -X POST localhost:8080/api/v1/cards -H 'Content-Type: application/json' -d '{
  "name":"HSBC Revolution","last4":"8842","network":"Visa","track":"miles",
  "termsUrl":"https://issuer.example/terms.pdf"}'
```

Also: `POST /api/v1/cards/{card_id}/recheck` re-reads the stored link, and
`POST /api/v1/cards/{card_id}/terms` accepts a PDF upload.

### The cases worth trying

| Try | What should happen |
|---|---|
| A terms PDF | `parsed`, rules with MCC codes and caps |
| An issuer's marketing page | Usually `no_rules_found` — see limitations |
| A 404 link | `failed`, reason `fetch_failed` |
| Text with no rates | `failed`, reason `no_rules_found` |
| DBS yuu terms, `track: cashback` vs `points` | Same card, different primary rate, alternative shown |
| UOB Lady's terms | `requiresSelection` true, the category menu, exclusions |

**The behaviour to check hardest:** give it an issuer page whose rates load via
JavaScript. It must return `no_rules_found`, *not* rates recited from training
data. I verified this against the real DBS Live Fresh page. If it ever starts
inventing rates, that is the bug that matters most.

---

## 5. Known limitations

**Most issuer web pages will not work.** Banks render rates in JavaScript, so
fetching returns navigation chrome. The agent reports this honestly rather than
guessing, but in practice **PDFs are the reliable path**. Fixing this properly
needs a headless browser in the fetch step — a real dependency, and a separate
piece of work.

**Extraction is not deterministic.** The same document read twice does not
produce the same answer, even at temperature 0. Two passes are merged to
recover most of it (see 5b), but a third pass would recover a little more, and
some structures still only surface sometimes. Treat any single reading as
provisional — which is exactly why the interface shows the user what was read
before it drives anything.

**The valuations are placeholders.** Every figure in `app/valuations.py` carries
its own reasoning string saying so, and there is a test that fails if anyone
adds one without stating why. They need real numbers before any of this is
presented as advice — KrisFlyer first, since most local cards feed into it.

**Reward-option divergence is detected, not resolved.** When a card pays the
same reward two ways and they price far apart, that is flagged in `unresolved`.
It means a conversion was misread; it does not fix it.

**Nothing schedules rechecks.** The endpoint works, the orchestrator does not
call it on a cycle.

**The PDF upload endpoint has no UI.** The form takes a URL only.

---

## 5b. Extraction quality, measured

`backend/evals/` holds ten reward structures chosen to break the schema —
nominated categories, rotating categories, transaction-count conditions, spend
tiers, relationship multipliers, statement credits, reward-currency choice.

```bash
cd backend && source .venv/bin/activate && python -m evals.run_extraction_eval
```

It calls Gemini, so it costs money and takes a few minutes. Run it after
changing the schema or the prompt.

**Capture rate went from 7/10 to 9/10.** The single most useful finding was
that repeated runs of the same document disagree: across three baseline runs
capture moved between 70% and 80% and *the misses moved too* — a run that
dropped a nomination requirement caught a spend-elsewhere condition, and the
next did the reverse.

Because those misses are uncorrelated, extraction now runs **twice and merges
the passes additively** (`app/agents/consolidate.py`). A condition either pass
found is kept; a rule only one pass saw is not promoted, so merging never
invents coverage. Card intelligence runs weekly per card, so the second call is
cheap. Set `EXTRACTION_PASSES=1` to disable.

The eval also caught two regressions I introduced: a stricter prompt made UOB
One fail outright, because its value is a fixed quarterly rebate rather than a
rate — benefits-only cards are now valid extractions — and a benefits-only pass
was being discarded during merging.

## 6. Next steps

Roughly in order of value:

~~1. Fill missing MCC codes from a curated map~~ — done, `app/mcc.py`.
~~3. Wire the weekly recheck into the orchestrator~~ — done; cards past
`nextRecheckAt` are reread before the optimiser prices anything.
~~5. File picker for local PDFs~~ — done.
~~6. Feed `conditional-rate` into the advisory agent~~ — done; a conditional
rate now produces a "unlock the bonus rate" recommendation, and an unreadable
card produces one telling you it is excluded.

Still open:

1. **Confirm the reward valuations.** One file, immediate effect on every
   figure in the product. The divergence check already caught one error here:
   UNI$ was priced at one mile when it transfers at two.
2. **Decide on headless rendering** for JavaScript issuer pages, or accept
   PDF-only and say so in the interface.
3. **Use benefit conditions in the optimiser.** They are structured now — a
   UOB One rebate carries its spend threshold and transaction count — but
   strategy does not yet evaluate them.
4. **Track eval results over time** so a prompt change that helps one card and
   breaks another is visible.

### Still open

- What should the Singapore reward valuations actually be? KrisFlyer, DBS
  Points, UNI$ and Membership Rewards are the ones that matter.
- The frontend exists in two repos (`hcy-05/CardSense` and this one). This
  branch changes the copy in `CardSenseFrontend/`. Worth consolidating before
  they diverge further.
