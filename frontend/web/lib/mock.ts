import type { Snapshot } from "./types";

/**
 * Placeholder snapshot. Numbers are invented but internally consistent:
 * category `captured`/`unclaimed` sum to the figures in `totals`.
 *
 * Every edge case in the product brief is represented here on purpose, so the
 * UI is built against the awkward states rather than the happy path:
 * a cap reached mid-cycle, a tie between two cards, a sign-up bonus deadline,
 * a reward-rules PDF that failed to parse, an ambiguous merchant, a
 * transaction spanning two MCCs, and no stated track preference.
 */
export const snapshot: Snapshot = {
  generatedAt: "2026-08-08T07:12:00-04:00",
  period: {
    label: "Quarter to date",
    start: "2026-07-01",
    end: "2026-08-08",
  },

  totals: {
    spend: 14_480.55,
    refunds: 0,
    netSpend: 14_480.55,
    captured: 198.65,
    unclaimed: 219.85,
  },

  agents: [
    {
      id: "ingestion",
      label: "Ingestion",
      status: "ok",
      lastRunAt: "2026-08-08T07:04:00-04:00",
    },
    {
      id: "forecast",
      label: "Forecast",
      status: "ok",
      lastRunAt: "2026-08-08T07:06:00-04:00",
    },
    {
      id: "card-intelligence",
      label: "Card intelligence",
      status: "degraded",
      lastRunAt: "2026-08-08T07:09:00-04:00",
      note: "Meridian Signature terms PDF did not parse. Rewards for that card are excluded from every figure on this page.",
    },
    {
      id: "strategy",
      label: "Simulation & strategy",
      status: "ok",
      lastRunAt: "2026-08-08T07:11:00-04:00",
    },
    {
      id: "advisory",
      label: "Advisory",
      status: "ok",
      lastRunAt: "2026-08-08T07:12:00-04:00",
    },
  ],

  recommendations: [
    {
      id: "rec-dining-cap",
      urgency: "act-now",
      headline: "Move dining to Sapphire Reserve — for the next $18 only",
      card: { name: "Sapphire Reserve", last4: "4471" },
      impact: 64.21,
      impactWindow: "per quarter",
      body:
        "Dining is your largest leak. Sapphire Reserve pays 4× points there versus the 1% you are earning on Everyday Blue. The catch: $1,482 of its $1,500 quarterly cap is already spent, so only about $18 of dining still earns the bonus rate. After that, every card you hold pays the same on dining.",
      trace: [
        {
          agent: "ingestion",
          detail:
            "Grouped 84 transactions under MCC 5812 (eating places) totalling $2,140.20; 79 of them settled on Everyday Blue ••9012.",
        },
        {
          agent: "card-intelligence",
          detail:
            "Sapphire Reserve terms (PDF, retrieved 4 Aug) — 4× points on MCC 5812, capped at $1,500 spend per calendar quarter, then 1×.",
        },
        {
          agent: "strategy",
          detail:
            "Optimal-card simulation across 9 cards: dining earned $21.40, optimal $85.61, gap $64.21. Remaining bonus-rate headroom this quarter is $18.00.",
        },
        {
          agent: "advisory",
          detail:
            "Flagged act-now because the headroom expires 30 Sep and is small enough to be spent in a single meal.",
        },
      ],
    },
    {
      id: "rec-bonus-deadline",
      urgency: "act-now",
      headline: "Spend $340 more on Horizon Miles by 24 Aug",
      card: { name: "Horizon Miles", last4: "3388" },
      impact: 600,
      impactWindow: "one-time bonus",
      deadline: "2026-08-24",
      body:
        "The 60,000-mile sign-up bonus needs $4,000 of spend in the first 90 days. You are at $3,660. Your forecast puts you at $3,910 by the deadline on current trends — $90 short. Routing one grocery run to this card closes the gap.",
      trace: [
        {
          agent: "card-intelligence",
          detail:
            "Horizon Miles offer terms — 60,000 miles after $4,000 spend within 90 days of account opening (26 May 2026). Deadline 24 Aug 2026.",
        },
        {
          agent: "ingestion",
          detail: "Qualifying spend to date on ••3388: $3,660.00.",
        },
        {
          agent: "forecast",
          detail:
            "Projected spend on this card by 24 Aug: $3,910 (based on the last 6 weeks, plus the trip you flagged for 19–22 Aug).",
        },
        {
          agent: "strategy",
          detail:
            "60,000 miles × $0.0130 = $780 nominal. Net of the $180 annual fee, the bonus is worth $600.",
        },
      ],
    },
    {
      id: "rec-grocery-tie",
      urgency: "this-week",
      headline: "Groceries: two cards are tied — pick either",
      card: { name: "Cashback One", last4: "7726" },
      tiedWith: { name: "Everyday Blue", last4: "9012" },
      impact: 49.66,
      impactWindow: "per quarter",
      body:
        "Both cards return $0.06 per dollar on groceries once points are converted to nominal value, and neither is near its cap. There is no better answer here, so the strategy agent is not inventing one. Everyday Blue keeps the reward in cash; Cashback One earns points that only beat cash if you redeem them for travel.",
      trace: [
        {
          agent: "strategy",
          detail:
            "Nominal return on $3,310.80 of MCC 5411 spend: Cashback One $198.65, Everyday Blue $198.65. Difference is under the $0.01 tie threshold.",
        },
        {
          agent: "advisory",
          detail:
            "Presented as a tie rather than ranked, and surfaced the redemption difference as the tiebreaker the user is best placed to judge.",
        },
      ],
    },
  ],

  categories: [
    {
      mcc: "5812",
      category: "Dining & restaurants",
      spend: 2_140.2,
      captured: 21.4,
      unclaimed: 64.21,
      usedCard: "Everyday Blue ••9012",
      bestCard: "Sapphire Reserve ••4471",
    },
    {
      mcc: "5411",
      category: "Groceries",
      spend: 3_310.8,
      captured: 33.11,
      unclaimed: 49.66,
      usedCard: "Everyday Blue ••9012",
      bestCard: "Cashback One ••7726",
      note: "Tied with Everyday Blue ••9012.",
    },
    {
      mcc: "3000–3299",
      category: "Air travel",
      spend: 1_980,
      captured: 19.8,
      unclaimed: 39.6,
      usedCard: "Everyday Blue ••9012",
      bestCard: "Horizon Miles ••3388",
    },
    {
      mcc: "5399",
      category: "Online retail",
      spend: 2_455.4,
      captured: 49.11,
      unclaimed: 24.55,
      usedCard: "Cashback One ••7726",
      bestCard: "Cashback One ••7726",
      flags: ["multi-mcc"],
      note: "A $612.40 warehouse-club order was split across groceries and general retail at the line-item level.",
    },
    {
      mcc: "4121",
      category: "Transit & rideshare",
      spend: 780.15,
      captured: 7.8,
      unclaimed: 15.6,
      usedCard: "Everyday Blue ••9012",
      bestCard: "Sapphire Reserve ••4471",
      flags: ["ambiguous-merchant"],
      note: "“CITY MOBILITY LLC” could be transit (4111) or rideshare (4121). Counted as rideshare; the two rates differ by $3.90 here.",
    },
    {
      mcc: "5815",
      category: "Streaming & digital",
      spend: 412.6,
      captured: 4.13,
      unclaimed: 12.38,
      usedCard: "Everyday Blue ••9012",
      bestCard: "Cashback One ••7726",
    },
    {
      mcc: "5541",
      category: "Fuel",
      spend: 690.4,
      captured: 13.81,
      unclaimed: 6.9,
      usedCard: "Cashback One ••7726",
      bestCard: "Sapphire Reserve ••4471",
    },
    {
      mcc: "4900",
      category: "Utilities & bills",
      spend: 711,
      captured: 7.11,
      unclaimed: 4.27,
      usedCard: "Everyday Blue ••9012",
      bestCard: "Everyday Blue ••9012",
      flags: ["rules-unverified"],
      note: "Meridian Signature ••5504 may pay more here, but its terms PDF did not parse, so it was left out of the comparison.",
    },
    {
      mcc: "—",
      category: "Everything else",
      spend: 2_000,
      captured: 42.38,
      unclaimed: 2.68,
      usedCard: "Mixed",
      bestCard: "Mixed",
    },
  ],

  cards: [
    {
      name: "Sapphire Reserve",
      last4: "4471",
      network: "Visa Infinite",
      categoryLabel: "Dining",
      rate: "4× points",
      cycleSpend: 1_482,
      cap: 1_500,
      cycleLabel: "quarterly cap",
      state: "approaching",
      note: "$18 of bonus-rate spend left. Resets 1 Oct.",
    },
    {
      name: "Everyday Blue",
      last4: "9012",
      network: "Mastercard",
      categoryLabel: "Groceries",
      rate: "6% cash back",
      cycleSpend: 1_500,
      cap: 1_500,
      cycleLabel: "quarterly cap",
      state: "reached",
      note: "Cap reached 22 Jul. Grocery spend since then has earned 1%.",
    },
    {
      name: "Horizon Miles",
      last4: "3388",
      network: "Amex",
      categoryLabel: "Air travel",
      rate: "3× miles",
      cycleSpend: 1_980,
      cap: null,
      cycleLabel: "no cap",
      state: "healthy",
    },
    {
      name: "Cashback One",
      last4: "7726",
      network: "Visa Signature",
      categoryLabel: "Online retail",
      rate: "2% cash back",
      cycleSpend: 990.2,
      cap: 2_500,
      cycleLabel: "quarterly cap",
      state: "healthy",
    },
    {
      name: "Meridian Signature",
      last4: "5504",
      network: "Mastercard World",
      categoryLabel: "Utilities",
      rate: "Unknown",
      cycleSpend: 711,
      cap: null,
      cycleLabel: "terms unread",
      state: "unverified",
      note: "Terms PDF returned no extractable text. Excluded from every comparison until it parses.",
    },
  ],

  tracks: [
    {
      track: "points",
      rawUnits: 24_180,
      unitLabel: "points",
      rate: 0.01,
      nominal: 241.8,
      source: "Placeholder rate — confirm against issuer transfer charts before the demo.",
    },
    {
      track: "cashback",
      rawUnits: 186.4,
      unitLabel: "dollars",
      rate: 1,
      nominal: 186.4,
      source: "Cash back is already denominated in dollars. No conversion applied.",
    },
    {
      track: "miles",
      rawUnits: 18_900,
      unitLabel: "miles",
      rate: 0.013,
      nominal: 245.7,
      source: "Placeholder rate — confirm against issuer transfer charts before the demo.",
    },
  ],

  trackPreference: null,
  recommendedTrack: "miles",
  trackRationale:
    "Air travel and dining are two of your three largest categories, and both of your highest-earning cards accrue miles. Miles come out ahead of points by $3.90 a quarter — close enough that the real deciding factor is whether you will actually redeem for flights. If you would rather not think about redemption at all, take cash back and give up about $59 a quarter.",

  /* ------------------------------------------------------------ forecast -- */

  forecast: {
    horizonDays: 31,
    horizonMonths: 1,
    baselineSpend: 3_420,
    variableSpend: 2_180,
    recurringSpend: 1_240,
    plannedSpend: 1_400,
    projectedSpend: 4_820,
    historyDays: 42,
    quality: "good",
    confidence: 610,
    reliableMonths: 4,
    extrapolated: false,
    basis:
      "Six weeks of transaction history, plus one event you declared. Not seasonality — there is not enough history yet to claim that.",
    months: [
      {
        month: "2026-09",
        label: "Sep 2026",
        days: 31,
        variable: 2_180,
        recurring: 1_240,
        planned: 1_400,
        total: 4_820,
        cumulative: 4_820,
        cumulativeConfidence: 610,
      },
    ],
    categories: [
      { category: "Rent", mcc: "6513", variable: 0, recurring: 950, planned: 0, projected: 950, monthly: 933, share: 0.1971 },
      { category: "Air travel", mcc: "4511", variable: 120, recurring: 0, planned: 700, projected: 820, monthly: 805, share: 0.1701 },
      { category: "Dining", mcc: "5812", variable: 640, recurring: 0, planned: 0, projected: 640, monthly: 628, share: 0.1328 },
      { category: "Groceries", mcc: "5411", variable: 520, recurring: 0, planned: 0, projected: 520, monthly: 511, share: 0.1079 },
    ],
    recurring: [
      { merchant: "GREYSTONE PROPERTY", category: "Rent", cadence: "monthly", amount: 950, monthlyAmount: 950, occurrences: 3, nextDue: "2026-09-01", confidence: "high", kind: "bill" },
      { merchant: "CON EDISON", category: "Utilities", cadence: "monthly", amount: 118, monthlyAmount: 118, occurrences: 3, nextDue: "2026-09-04", confidence: "medium", kind: "bill" },
      { merchant: "NETFLIX", category: "Streaming", cadence: "monthly", amount: 15.49, monthlyAmount: 15.49, occurrences: 2, nextDue: "2026-09-06", confidence: "low", kind: "bill" },
    ],
    doNothingCost: 180,
    doNothingWindow: "over the next month",
    timeline: [
      {
        date: "2026-08-11",
        kind: "agent",
        title: "Card intelligence rechecks 9 terms documents",
        detail:
          "Weekly cadence. Any rate change re-runs the strategy simulation the same night.",
      },
      {
        date: "2026-08-19",
        kind: "event",
        title: "Lisbon trip",
        detail: "You declared 19–22 Aug.",
        amount: 1_400,
        action: "Put flights and hotels on Horizon Miles ••3388.",
      },
      {
        date: "2026-08-21",
        kind: "cap",
        title: "Dining passes Sapphire Reserve's 4× cap",
        detail:
          "Projected to cross mid-trip. After this, Sapphire pays the same on dining as every other card you hold.",
        action: "Switch dining to Cashback One ••7726 from this date.",
      },
      {
        date: "2026-08-24",
        kind: "deadline",
        title: "Horizon Miles sign-up bonus closes",
        detail: "$340 of qualifying spend still needed on ••3388.",
        amount: 600,
        action: "One grocery run on that card covers the gap.",
      },
      {
        date: "2026-09-01",
        kind: "reset",
        title: "Everyday Blue grocery cap resets",
        detail: "6% on groceries returns, up to $1,500 for the cycle.",
      },
      {
        date: "2026-09-14",
        kind: "purchase",
        title: "Replacement laptop",
        detail: "You declared this.",
        amount: 2_400,
      },
      {
        date: "2026-09-14",
        kind: "cap",
        title: "Online retail passes Cashback One's cap",
        detail:
          "$990 of the $2,500 quarterly cap is already used, so the laptop takes it past on its own.",
        action:
          "Split it — $1,510 on Cashback One ••7726, the remainder on Everyday Blue ••9012.",
      },
      {
        date: "2026-09-30",
        kind: "reset",
        title: "Quarter closes",
        detail:
          "Every quarterly cap resets. Unused headroom does not carry over — it is simply gone.",
      },
    ],
  },

  /* ---------------------------------------------------------------- goal -- */

  goal: {
    track: "miles",
    target: 120_000,
    unitLabel: "miles",
    current: 18_900,
    deadline: "2027-01-01",
    purpose: "Two business-class seats to Tokyo",
    pacePerMonth: 14_900,
    projectedAt: "2027-03-03",
    fix: {
      action: "Move dining and groceries to Horizon Miles ••3388",
      pacePerMonth: 22_300,
      projectedAt: "2026-12-24",
    },
  },

  /* ------------------------------------------------------ planned spend -- */

  planned: [
    {
      id: "plan-lisbon",
      kind: "event",
      label: "Lisbon trip",
      startDate: "2026-08-19",
      endDate: "2026-08-22",
      amount: 1_400,
      categories: ["Air travel", "Dining & restaurants"],
      note: "Flights already booked; the estimate covers hotels and meals.",
    },
    {
      id: "plan-laptop",
      kind: "purchase",
      label: "Replacement laptop",
      startDate: "2026-09-14",
      amount: 2_400,
      categories: ["Online retail"],
    },
  ],

  /* -------------------------------------------------------- track record -- */

  trackRecord: {
    taken: 5,
    offered: 10,
    earned: 258.4,
    missed: 29.3,
    accuracyNote:
      "Across 5 closed recommendations, predictions have landed within 6% of actual on average.",
    records: [
      {
        id: "adv-dining-cap",
        outcome: "open",
        pushedAt: "2026-08-08",
        headline: "Move dining to Sapphire Reserve — for the next $18 only",
        card: { name: "Sapphire Reserve", last4: "4471" },
        predicted: 64.21,
        window: "per quarter",
      },
      {
        id: "adv-bonus",
        outcome: "open",
        pushedAt: "2026-08-08",
        headline: "Spend $340 more on Horizon Miles by 24 Aug",
        card: { name: "Horizon Miles", last4: "3388" },
        predicted: 600,
        window: "one-time bonus",
      },
      {
        id: "adv-tie",
        outcome: "open",
        pushedAt: "2026-08-08",
        headline: "Groceries: two cards are tied — pick either",
        card: { name: "Cashback One", last4: "7726" },
        predicted: 49.66,
        window: "per quarter",
      },
      {
        id: "adv-grocery-blue",
        outcome: "acted",
        pushedAt: "2026-07-01",
        resolvedAt: "2026-07-22",
        headline: "Switch groceries to Everyday Blue",
        card: { name: "Everyday Blue", last4: "9012" },
        predicted: 48,
        actual: 41.8,
        window: "for the cycle",
        gapReason:
          "You hit the 6% cap eight days earlier than projected — a $310 warehouse-club order landed in the same cycle and the forecast had not seen one before.",
      },
      {
        id: "adv-flight",
        outcome: "acted",
        pushedAt: "2026-07-09",
        resolvedAt: "2026-07-14",
        headline: "Route the flight booking to Horizon Miles",
        card: { name: "Horizon Miles", last4: "3388" },
        predicted: 78,
        actual: 81.9,
        window: "one-time",
        gapReason:
          "The fare came in above the forecast, so the 3× multiplier earned more than predicted.",
      },
      {
        id: "adv-grocery-meridian",
        outcome: "acted",
        pushedAt: "2026-05-30",
        resolvedAt: "2026-06-30",
        headline: "Stop putting groceries on Meridian Signature",
        card: { name: "Everyday Blue", last4: "9012" },
        predicted: 96,
        actual: 88.3,
        window: "per quarter",
        gapReason: "Grocery spend ran 8% below forecast through June.",
      },
      {
        id: "adv-insurance",
        outcome: "acted",
        pushedAt: "2026-06-12",
        resolvedAt: "2026-06-15",
        headline: "Put the annual insurance premium on Cashback One",
        card: { name: "Cashback One", last4: "7726" },
        predicted: 34,
        actual: 34,
        window: "one-time",
      },
      {
        id: "adv-streaming",
        outcome: "acted",
        pushedAt: "2026-06-28",
        resolvedAt: "2026-07-05",
        headline: "Move streaming subscriptions to Cashback One",
        card: { name: "Cashback One", last4: "7726" },
        predicted: 12.4,
        actual: 12.4,
        window: "per quarter",
      },
      {
        id: "adv-q2-dining",
        outcome: "expired",
        pushedAt: "2026-06-26",
        resolvedAt: "2026-06-30",
        headline: "Q2 dining headroom went unused",
        predicted: 22.4,
        actual: 0,
        window: "for the quarter",
        gapReason:
          "Pushed four days before the quarter closed. That was too late to act on, and the advisory agent now raises cap headroom at 60% rather than 90%.",
      },
      {
        id: "adv-fuel",
        outcome: "dismissed",
        pushedAt: "2026-07-15",
        resolvedAt: "2026-07-15",
        headline: "Consider moving fuel to Sapphire Reserve",
        card: { name: "Sapphire Reserve", last4: "4471" },
        predicted: 6.9,
        window: "per quarter",
        gapReason:
          "You dismissed this. Recommendations worth under $10 a quarter are no longer pushed.",
      },
    ],
  },

  /* -------------------------------------------------------------- wallet -- */

  wallet: [
    {
      name: "Sapphire Reserve",
      last4: "4471",
      network: "Visa Infinite",
      annualFee: 550,
      track: "points",
      rules: [
        { categoryLabel: "Dining", rate: "4× points", cap: 1_500, cycleLabel: "per quarter" },
        { categoryLabel: "Travel", rate: "3× points", cap: null, cycleLabel: "no cap" },
        { categoryLabel: "Everything else", rate: "1× point", cap: null, cycleLabel: "no cap" },
      ],
      source: {
        label: "Sapphire Reserve terms & conditions",
        locator: "terms-sapphire-2026.pdf · page 4",
        retrievedAt: "2026-08-04",
      },
      recheckCadence: "Weekly",
      nextRecheckAt: "2026-08-11",
      parseStatus: "parsed",
    },
    {
      name: "Everyday Blue",
      last4: "9012",
      network: "Mastercard",
      annualFee: 0,
      track: "cashback",
      rules: [
        { categoryLabel: "Groceries", rate: "6% cash back", cap: 1_500, cycleLabel: "per quarter" },
        { categoryLabel: "Everything else", rate: "1% cash back", cap: null, cycleLabel: "no cap" },
      ],
      source: {
        label: "Everyday Blue cardholder agreement",
        locator: "everydayblue-terms.pdf · page 2",
        retrievedAt: "2026-08-04",
      },
      recheckCadence: "Weekly",
      nextRecheckAt: "2026-08-11",
      parseStatus: "parsed",
    },
    {
      name: "Horizon Miles",
      last4: "3388",
      network: "Amex",
      annualFee: 180,
      track: "miles",
      rules: [
        { categoryLabel: "Air travel", rate: "3× miles", cap: null, cycleLabel: "no cap" },
        { categoryLabel: "Dining", rate: "2× miles", cap: null, cycleLabel: "no cap" },
        { categoryLabel: "Everything else", rate: "1× mile", cap: null, cycleLabel: "no cap" },
      ],
      source: {
        label: "Horizon Miles benefits guide",
        locator: "horizon-benefits.html",
        retrievedAt: "2026-08-04",
      },
      recheckCadence: "Weekly",
      nextRecheckAt: "2026-08-11",
      parseStatus: "parsed",
    },
    {
      name: "Cashback One",
      last4: "7726",
      network: "Visa Signature",
      annualFee: 0,
      track: "cashback",
      rules: [
        { categoryLabel: "Online retail", rate: "2% cash back", cap: 2_500, cycleLabel: "per quarter" },
        { categoryLabel: "Streaming", rate: "3% cash back", cap: 500, cycleLabel: "per quarter" },
        { categoryLabel: "Everything else", rate: "1% cash back", cap: null, cycleLabel: "no cap" },
      ],
      source: {
        label: "Cashback One rates & fees",
        locator: "cashbackone.com/rates",
        retrievedAt: "2026-07-28",
      },
      recheckCadence: "Weekly",
      nextRecheckAt: "2026-08-11",
      parseStatus: "stale",
      parseNote:
        "The last successful read is 11 days old. The issuer page has returned a rate limit on the two most recent attempts, so these rules may be out of date.",
    },
    {
      name: "Meridian Signature",
      last4: "5504",
      network: "Mastercard World",
      annualFee: 95,
      track: "points",
      rules: [],
      source: {
        label: "Meridian Signature terms",
        locator: "meridian-terms.pdf · scanned",
        retrievedAt: "2026-08-04",
      },
      recheckCadence: "Weekly",
      nextRecheckAt: "2026-08-11",
      parseStatus: "failed",
      parseNote:
        "The PDF is a scanned image with no text layer, and document understanding returned no extractable rules. This card is excluded from every comparison until it parses.",
    },
  ],

  /* ------------------------------------------------------------- catalog -- */

  catalog: [
    {
      name: "Aurora Dining Card",
      network: "Visa",
      headlineRate: "4% cash back on dining, no cap",
      annualFee: 0,
      track: "cashback",
      held: false,
      deltaVsWallet: 61.4,
      deltaNote:
        "Your dining alone justifies it, and there is no cap to run into halfway through a quarter.",
      tags: ["dining", "no annual fee"],
    },
    {
      name: "Vantage Grocer",
      network: "Visa",
      headlineRate: "5% groceries up to $2,000 per quarter",
      annualFee: 49,
      track: "cashback",
      held: false,
      deltaVsWallet: 33.1,
      deltaNote:
        "A higher cap than Everyday Blue, which you reached on 22 Jul. Fee is covered by the second month at your grocery rate.",
      tags: ["groceries"],
    },
    {
      name: "Meridian Everyday",
      network: "Mastercard",
      headlineRate: "2% flat on everything",
      annualFee: 0,
      track: "cashback",
      held: false,
      deltaVsWallet: 12.8,
      deltaNote:
        "Beats your 1% catch-all, but loses to your category cards wherever they apply.",
      tags: ["flat rate", "no annual fee"],
    },
    {
      name: "Summit Fuel & Transit",
      network: "Mastercard",
      headlineRate: "4% fuel and transit",
      annualFee: 0,
      track: "cashback",
      held: false,
      deltaVsWallet: 9.6,
      deltaNote: "A small win — your fuel and transit spend is light.",
      tags: ["fuel", "transit", "no annual fee"],
    },
    {
      name: "Pinnacle Travel",
      network: "Amex",
      headlineRate: "3× miles on travel",
      annualFee: 95,
      track: "miles",
      held: false,
      deltaVsWallet: -18.2,
      deltaNote:
        "Your travel spend does not cover the annual fee at your current rate. It would at roughly $3,200 a quarter.",
      tags: ["travel", "miles"],
    },
    {
      name: "Sapphire Reserve",
      network: "Visa Infinite",
      headlineRate: "4× points on dining, 3× on travel",
      annualFee: 550,
      track: "points",
      held: true,
      deltaVsWallet: 0,
      tags: ["dining", "travel", "points"],
    },
    {
      name: "Everyday Blue",
      network: "Mastercard",
      headlineRate: "6% groceries up to $1,500 per quarter",
      annualFee: 0,
      track: "cashback",
      held: true,
      deltaVsWallet: 0,
      tags: ["groceries", "no annual fee"],
    },
    {
      name: "Horizon Miles",
      network: "Amex",
      headlineRate: "3× miles on air travel",
      annualFee: 180,
      track: "miles",
      held: true,
      deltaVsWallet: 0,
      tags: ["travel", "miles"],
    },
    {
      name: "Cashback One",
      network: "Visa Signature",
      headlineRate: "2% online retail, 3% streaming",
      annualFee: 0,
      track: "cashback",
      held: true,
      deltaVsWallet: 0,
      tags: ["online", "streaming", "no annual fee"],
    },
    {
      name: "Meridian Signature",
      network: "Mastercard World",
      headlineRate: "Rules not yet readable",
      annualFee: 95,
      track: "points",
      held: true,
      deltaVsWallet: 0,
      deltaNote: "Excluded from comparison — the terms document has not parsed.",
      tags: ["points"],
    },
  ],

  /* ------------------------------------------------------------ activity -- */

  activity: [
    {
      id: "run-0812-advisory",
      agent: "advisory",
      status: "ok",
      startedAt: "2026-08-08T07:12:00-04:00",
      durationMs: 1_240,
      summary: "Wrote 3 recommendations",
      detail:
        "Two flagged act-now, one this-week. Ranked by dollars at risk before the nearest deadline.",
      writes: "advice",
      reads: ["strategy_runs"],
    },
    {
      id: "run-0811-strategy",
      agent: "strategy",
      status: "ok",
      startedAt: "2026-08-08T07:11:00-04:00",
      durationMs: 4_830,
      summary: "Simulated 9 cards across 9 categories",
      detail:
        "81 card-category pairs priced to nominal dollars. Found $219.85 unclaimed this quarter against $198.65 captured.",
      writes: "strategy_runs",
      reads: ["transactions", "card_rules", "forecasts"],
    },
    {
      id: "run-0809-cardintel",
      agent: "card-intelligence",
      status: "degraded",
      startedAt: "2026-08-08T07:09:00-04:00",
      durationMs: 11_420,
      summary: "Parsed 8 of 9 terms documents",
      detail:
        "Meridian Signature ••5504 returned no extractable text — the PDF is a scanned image. Cashback One served a rate limit, so the 28 Jul copy was reused.",
      writes: "card_rules",
      retryable: true,
    },
    {
      id: "run-0806-forecast",
      agent: "forecast",
      status: "ok",
      startedAt: "2026-08-08T07:06:00-04:00",
      durationMs: 2_080,
      summary: "Projected 30 days of spending",
      detail:
        "Six weeks of history plus one declared event (Lisbon, 19–22 Aug). Projection $4,820 ± $610.",
      writes: "forecasts",
      reads: ["transactions"],
    },
    {
      id: "run-0804-ingestion",
      agent: "ingestion",
      status: "ok",
      startedAt: "2026-08-08T07:04:00-04:00",
      durationMs: 6_710,
      summary: "Ingested 842 transactions",
      detail:
        "Plaid sandbox, 4 linked accounts. Grouped into 9 MCC categories; 1 merchant flagged ambiguous for review.",
      writes: "transactions",
    },
    {
      id: "run-0707-advisory",
      agent: "advisory",
      status: "ok",
      startedAt: "2026-08-07T07:12:00-04:00",
      durationMs: 1_180,
      summary: "Wrote 2 recommendations",
      writes: "advice",
      reads: ["strategy_runs"],
    },
    {
      id: "run-0709-cardintel",
      agent: "card-intelligence",
      status: "ok",
      startedAt: "2026-08-07T07:09:00-04:00",
      durationMs: 9_640,
      summary: "Parsed 9 of 9 terms documents",
      detail: "Every document read cleanly on this run.",
      writes: "card_rules",
    },
  ],

  collections: [
    { collection: "transactions", writtenBy: "ingestion", readBy: ["forecast", "strategy"] },
    { collection: "forecasts", writtenBy: "forecast", readBy: ["strategy"] },
    { collection: "card_rules", writtenBy: "card-intelligence", readBy: ["strategy"] },
    { collection: "strategy_runs", writtenBy: "strategy", readBy: ["advisory"] },
    { collection: "advice", writtenBy: "advisory", readBy: [] },
  ],
};
