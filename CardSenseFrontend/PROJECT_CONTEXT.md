# CardSense — Project Context for Claude Code

This document summarizes all product, architecture, and scope decisions made so far, for use as context when starting implementation — particularly UI/UX design. Read this before generating any screens or components.

---

## 1. What This Is

CardSense is an autonomous, multi-agent system that analyzes a user's spending, matches it against credit card reward rules, and proactively recommends which card to use and when — without the user having to research card terms themselves. Built for the **All Things Agentic Hackathon** (Google Gemini + ADK), entered under the **Taskmaster** track ("build a complete workflow, not a chatbot — make an agent that takes action").

This is explicitly **not a chatbot**. The user doesn't ask it questions in the primary flow — it runs in the background and pushes recommendations to them.

## 2. Hackathon Constraints That Affect Design

- Must visibly demonstrate Gemini 3.5+ (via Vertex AI), Google ADK, and at least one GCP infra service (Cloud Run, Firestore, Pub/Sub) — the demo video needs to show this, so the UI should make the "agent did this autonomously" moment visible and legible to a judge watching a 4-minute video, not buried in a settings page.
- Judging weights: Innovation & Operational Utility 40%, Architectural Discipline & Tech Stack 30%, Demo & Production Readiness 30%. For UI/UX specifically, this means: prioritize clarity of *what the agent decided and why* over visual polish for its own sake. A judge should understand a recommendation's reasoning at a glance.
- Timeline: ~3.5 weeks total (started ~Aug 8, submission Aug 31, 2026). Team of 2, splitting agent ownership — see section 5.

## 3. Agent Architecture (backend, for reference)

| Agent | Job |
|---|---|
| **Ingestion Agent** | Pulls transactions (Plaid sandbox), categorizes by MCC, amount, merchant |
| **Forecast Agent** | Projects near-term spending from recent trends + user-declared upcoming life events (explicitly NOT statistical seasonality detection — sandbox data is too sparse for that to be credible) |
| **Card Intelligence Agent** | Parses reward rules from a fixed set of user-supplied PDF/webpage links (Gemini document understanding), rechecks periodically for updates |
| **Simulation & Strategy Agent** | Computes actual vs. optimal rewards across three tracks — points, cashback, air miles — converts all to nominal dollar value, recommends best track if user has no preference, flags diminishing returns on capped categories |
| **Advisory Agent** | Converts strategy output into plain-language recommendations, pushed to dashboard and browser extension |

All agents share a Firestore schema rather than calling each other directly.

## 4. Product Surfaces to Design

### A. Web Dashboard (MVP: one page, Spending Analytics)
- Most-spent MCC categories, visualized
- Rewards actually earned vs. rewards missed (the "here's what optimizing would have gotten you" gap — this is the core emotional hook of the product, should be prominent)
- Per-card utilization (how close to any spending cap)
- Recommended reward track (points/cashback/miles) and why, if the user hasn't set a preference
- Design north star: this should read like a "here's money you left on the table" moment, not a generic finance dashboard

### B. Chrome Extension (recommend-only — see hard constraint below)
- Detects merchant on a checkout page
- Shows a small popup: which card to use, why (e.g., "4x points on dining here — you're not near your cap"), which card by name/last-4-digits
- **Hard constraint: never auto-fills or stores an actual card number.** This is a security/PCI liability and out of scope for what's being built. The UI should make clear this is advisory only — the user manually selects and enters their own card.

### C. (Post-MVP / roadmap only, not for initial build) Full dashboard with Cards page and Settings page — do not design these yet unless MVP is ahead of schedule.

## 5. Team & Ownership

- Teammate A: Ingestion Agent + Forecast Agent
- Teammate B: Card Intelligence Agent + Simulation/Strategy Agent
- Both: Advisory Agent, integration

## 6. Explicit Scope Boundaries (do not design or build beyond these for MVP)

**In scope:**
- Plaid sandbox data (not production)
- ~8-10 hardcoded/PDF-seeded cards (not open-ended scraping)
- 3-track reward conversion to nominal value
- Dashboard: single Spending Analytics page
- Chrome extension: recommend-only popup

**Out of scope (roadmap, not MVP):**
- Real-time production Plaid integration
- Open-ended internet scraping beyond specific fed URLs
- Auto-filling/auto-submitting real card numbers at checkout
- Full 4-page dashboard (Dashboard / Analytics / Cards / Settings)
- Third-party rent/loan-to-spend conversion (e.g. CardUp)

## 7. Disclaimer Requirement

Product is informational only, not licensed financial advice. This should appear somewhere visible in the UI (e.g. dashboard footer, extension popup first-use), not just buried in a README.

## 8. Test Cases the UI Should Handle Gracefully

- A transaction spanning multiple MCC categories
- A reward cap hit mid-month
- A sign-up bonus with an approaching deadline
- A PDF that fails to parse (Card Intelligence Agent degrades gracefully)
- An ambiguous merchant that could map to multiple MCCs
- Two cards tied for best nominal value
- No stated reward-track preference from the user

## 9. Reward Track Conversion Assumptions (placeholder — confirm real source before demo)

- Cashback: 1:1 (already dollars)
- Points: ~$0.01/point
- Miles: ~$0.013/mile

State the source for these explicitly in the UI or docs — an unstated assumption undermines the "optimal" framing.

---

## Ask for Claude Code

Please help design the UI/UX for surfaces A (dashboard) and B (Chrome extension popup) per the scope above, starting with the dashboard's Spending Analytics page. Keep visual design in line with a fast-moving hackathon build — clean and legible over heavily polished — and prioritize surfacing agent reasoning (why a recommendation was made) over pure aesthetics, since that maps directly to judging criteria.
