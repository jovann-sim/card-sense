# CardSense — Agentic Credit Card Reward Optimizer

> Built for the **All Things Agentic Hackathon** (Google Gemini + ADK) — Track: **The Taskmaster**

## The Problem

Credit card rewards programs are deliberately hard to optimize. Reward categories, MCC (Merchant Category Code) mappings, spending caps, and sign-up bonuses are scattered across dozens of PDFs and T&Cs pages. Most people default to using one or two cards for everything, silently leaving reward value on the table every month — not because they don't care, but because doing the math themselves is tedious and never-ending (issuers change terms constantly).

## What CardSense Does

CardSense is an **autonomous, multi-agent workflow** that removes this research burden entirely. It ingests a user's spending, matches it against a live-updated database of card reward structures, simulates which combination of cards would have maximized (and will maximize) rewards, and proactively tells the user how to change their strategy — without the user ever having to read a single T&Cs PDF.

This is not a chatbot. The user does not "ask" CardSense anything. It runs in the background, analyzes on its own schedule, and pushes recommendations to the user.

## Agent Architecture

CardSense is built as a pipeline of cooperating agents orchestrated with **Google ADK**, each with a narrow, well-defined job — not one monolithic prompt trying to do everything.

| Agent | Owner | Job | Trigger |
|---|---|---|---|
| **Ingestion Agent** | [Teammate A] | Pulls transaction data (via Plaid **sandbox**, or a CSV upload for demo purposes), normalizes and categorizes each transaction by MCC code, amount, and merchant | Scheduled / on new transaction webhook |
| **Forecast Agent** | [Teammate A] | Projects near-term spending using recent category trends **plus user-declared upcoming events** (e.g. "holiday shopping," "moving," "new job") — not statistical seasonality detection, which sparse sandbox data can't support credibly | Triggered after ingestion |
| **Card Intelligence Agent** | [Teammate B] | Ingests reward rules from a fixed set of **user-supplied PDF/webpage links** (Gemini's native document understanding parses T&Cs into structured MCC → reward-rate JSON). A scheduled job (Cloud Scheduler → Pub/Sub) re-checks the same known URLs periodically and re-parses on change, rather than open-ended crawling | Manual seed + scheduled diff-check |
| **Simulation & Strategy Agent** | [Teammate B] | Runs the user's transaction + forecast data against every card in the database. Supports three optimization tracks — **points, cashback, air miles** — and converts all three to a nominal dollar value using a stated conversion methodology, so it can recommend the best track when the user has no preference. Flags diminishing-returns situations (e.g., overusing a capped category) | Triggered after ingestion + forecast |
| **Advisory Agent** | [Both] | Turns the Strategy Agent's output into a plain-language recommendation ("Use Card X for groceries — you're 80% toward your cap on Card Y") and pushes it to the dashboard **and** the browser extension | Triggered after simulation completes |

All agents communicate through a shared Firestore schema rather than calling each other directly — agree on the transaction object and card-reward-rule object shape **before** writing agent logic, since that's the seam where a two-person split usually breaks.

### Reward Track Conversion (fill in your actual assumed rates)
- Cashback: 1:1, already in dollars
- Points: 1 point ≈ $0.01 (adjust to your source)
- Miles: 1 mile ≈ $0.013 (adjust to your source)

State your source for these in the demo — judges will accept an assumption if it's explicit, not if it's silently baked in.

## Tech Stack (hackathon requirements)

- **Model:** Gemini 3.5 (via Vertex AI) — used for categorization reasoning, strategy synthesis, and natural-language recommendation generation
- **Agent Framework:** Google ADK — orchestrates the four-agent pipeline and manages agent-to-agent handoffs
- **Google Cloud infra:** Firestore (transaction + card-database storage), Cloud Run (hosting the agent pipeline and API), Pub/Sub (event trigger between Ingestion → Simulation agents)
- **Data source:** Plaid (Sandbox environment for the demo — see Scope Decisions)
- **Frontend:** [React dashboard / Chrome extension — fill in based on what you actually build]

## MVP Scope for the Hackathon (read this before building)

Building all four agents *and* a full 4-page dashboard *and* live web scraping *and* real Plaid production data *and* a checkout-time browser extension is not realistic for a weekend with two people who are new to agent development. This is the scoped-down version that is actually finishable and demoable:

**In scope:**
- Ingestion Agent working against **Plaid sandbox data** (fake but realistic transactions)
- Forecast Agent projecting near-term spending from recent trends + user-declared life events (not statistical seasonality)
- A **fixed, curated set of ~8–10 real credit cards**, seeded via the Card Intelligence Agent parsing PDF/webpage links you feed it (not open-ended crawling)
- Simulation Agent computing actual vs. optimal rewards across all three tracks (points/cashback/miles), converted to a nominal dollar value, for the sandbox transaction history
- Advisory Agent producing a natural-language recommendation, delivered to a dashboard notification
- **Chrome extension** that detects the merchant on a checkout page and shows a popup recommendation ("Use Card X ending in 4821") — **recommendation only; it never auto-fills or stores an actual card number**, both because that's a major security/PCI liability and because automatic entry of payment credentials into forms is out of scope for what we're building
- One dashboard page: Spending Analytics (most-spent MCC categories, rewards earned vs. rewards missed)

**Explicitly out of scope for the hackathon (call these out as "Roadmap" in your writeup — judges respect an honest scope cut more than a broken ambitious build):**
- Real-time production Plaid integration
- Open-ended internet scraping beyond the specific URLs you feed the agent
- Auto-filling or auto-submitting real card numbers at checkout
- Full 4-page dashboard (Dashboard / Analytics / Cards / Settings)
- Third-party rent/loan-to-spend conversion strategies (e.g., CardUp)

## Disclaimer

CardSense provides informational spending analysis based on publicly available reward program terms. It is not a licensed financial advisor and does not provide personalized financial advice. Reward terms change frequently and users should verify current terms directly with their card issuer before making financial decisions.

## Setup / Spin-Up Instructions

```
# 1. Clone the repo
git clone <your-repo-url>
cd cardsense

# 2. Set up Google Cloud
gcloud auth login
gcloud config set project <your-project-id>

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
cp .env.example .env
# Fill in: GEMINI_API_KEY / VERTEX_PROJECT_ID, PLAID_CLIENT_ID (sandbox), PLAID_SECRET (sandbox)

# 5. Run locally
python main.py

# 6. (Optional) Deploy to Cloud Run
gcloud run deploy cardsense --source .
```

## Test / Stress Cases to Cover Before the Demo

- A purchase spanning multiple MCC categories in one transaction (e.g. Walmart groceries + electronics)
- A reward cap hit mid-month (does the agent correctly flag diminishing returns?)
- A sign-up bonus with a spending deadline approaching
- A PDF that fails to parse cleanly — does the agent degrade gracefully or crash the pipeline?
- An ambiguous merchant name that could map to more than one MCC
- Two cards tied for the best nominal value on a given track
- User has no stated track preference — does the recommendation logic pick a track and explain why?

## Team

- [Your name] — NUS, Computer Science & Mathematics (DDP) — Ingestion + Forecast Agents
- [Friend's name] — Card Intelligence + Simulation/Strategy Agents

## Findings & Learnings

[Fill in after building — judges specifically ask for this in the submission text description]
