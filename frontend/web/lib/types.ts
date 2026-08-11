/**
 * Data contract for the CardSense dashboard.
 *
 * The UI reads exactly this shape and nothing else. When the agents are live,
 * replace `lib/mock.ts` with a Firestore read that returns a `Snapshot` — no
 * component needs to change.
 */

export type ISODate = string;

export type AgentId =
  | "ingestion"
  | "forecast"
  | "card-intelligence"
  | "strategy"
  | "advisory";

/** `degraded` means the agent ran but could not complete every input. */
export type AgentStatus = "ok" | "degraded" | "running";

export interface AgentRun {
  id: AgentId;
  label: string;
  status: AgentStatus;
  lastRunAt: ISODate;
  /** Shown when status is not `ok`. Explains what the agent could not do. */
  note?: string;
}

export type RewardTrack = "points" | "cashback" | "miles";

export interface CardRef {
  name: string;
  last4: string;
}

export interface Period {
  label: string;
  start: ISODate;
  end: ISODate;
}

export interface Totals {
  /** Spending left out of the reward comparison, and why. */
  excludedSpend?: number;
  excludedCount?: number;
  uncategorisedSpend?: number;
  uncategorisedCount?: number;
  /** Bills a payment service could route onto a card for a fee. */
  redirectableSpend?: number;
  redirectableCount?: number;
  /** Posted purchase outflows, excluding refunds and credits. */
  spend: number;
  /** Absolute value of posted refunds and credits. */
  refunds: number;
  /** Gross spending minus refunds and credits. */
  netSpend: number;
  /** Rewards earned, in nominal dollars. */
  captured: number;
  /** Rewards the optimal card choice would have earned, minus captured. */
  unclaimed: number;
}

/** Conditions the UI has to render honestly rather than hide. */
export type CategoryFlag =
  | "multi-mcc"
  | "ambiguous-merchant"
  | "rules-unverified";

export interface CategoryLeak {
  mcc: string;
  category: string;
  spend: number;
  captured: number;
  unclaimed: number;
  usedCard: string;
  bestCard: string;
  flags?: CategoryFlag[];
  note?: string;
}

/** One link in the chain of agent decisions behind a recommendation. */
export interface ReasoningStep {
  agent: AgentId;
  detail: string;
}

export type Urgency = "act-now" | "this-week" | "informational";

export interface Recommendation {
  id: string;
  urgency: Urgency;
  /** The action, written as an imperative. */
  headline: string;
  card: CardRef | null;
  /** Set when a second card scores identically — the UI shows both. */
  tiedWith?: CardRef;
  impact: number;
  impactWindow: string;
  deadline?: ISODate;
  body: string;
  trace: ReasoningStep[];
}

export type CapState = "healthy" | "approaching" | "reached" | "unverified";

export interface CardCap {
  name: string;
  last4: string;
  network: string;
  categoryLabel: string;
  rate: string;
  cycleSpend: number;
  /** `null` means the card has no cap in this category. */
  cap: number | null;
  cycleLabel: string;
  state: CapState;
  note?: string;
}

export interface TrackValuation {
  track: RewardTrack;
  rawUnits: number;
  unitLabel: string;
  /** Dollars per unit. */
  rate: number;
  nominal: number;
  source: string;
}

/* -------------------------------------------------------------- forecast --- */

export type TimelineKind =
  | "event"
  | "purchase"
  | "cap"
  | "deadline"
  | "agent"
  | "reset";

export interface TimelineEntry {
  date: ISODate;
  kind: TimelineKind;
  title: string;
  detail?: string;
  /** What the user should do when this date arrives, if anything. */
  action?: string;
  amount?: number;
}

export type Cadence =
  | "weekly"
  | "fortnightly"
  | "monthly"
  | "quarterly"
  | "yearly";

/** One month of the projection, with the running total to the end of it. */
export interface ForecastMonth {
  month: string;
  label: string;
  days: number;
  variable: number;
  recurring: number;
  planned: number;
  total: number;
  cumulative: number;
  cumulativeConfidence: number;
}

export interface ForecastCategory {
  category: string;
  mcc: string;
  variable: number;
  recurring: number;
  planned: number;
  projected: number;
  monthly: number;
  share: number;
}

/** Spending detected as repeating on a schedule, projected by billing date. */
export interface RecurringStream {
  merchant: string;
  category: string | null;
  cadence: Cadence;
  amount: number;
  monthlyAmount: number;
  occurrences: number;
  nextDue: ISODate;
  confidence: "low" | "medium" | "high";
}

export interface Forecast {
  horizonDays: number;
  horizonMonths: number;
  /** History-derived spend: variable plus recurring, before declared plans. */
  baselineSpend: number;
  variableSpend: number;
  recurringSpend: number;
  plannedSpend: number;
  projectedSpend: number;
  historyDays: number;
  quality: "none" | "limited" | "good";
  /** Plus or minus, in dollars. Stated rather than hidden. */
  confidence: number;
  /** How far out the history genuinely supports projecting. */
  reliableMonths: number;
  /** True when the chosen horizon reaches past that point. */
  extrapolated: boolean;
  basis: string;
  months: ForecastMonth[];
  categories: ForecastCategory[];
  recurring: RecurringStream[];
  timeline: TimelineEntry[];
  doNothingCost: number;
  doNothingWindow: string;
}

/* ---------------------------------------------------------------- goal --- */

/**
 * A track on its own is a preference. A track with a target and a date is a
 * goal, and it changes what the strategy agent optimises for — which is why
 * the agent can say "you will miss this" rather than only "you left money out".
 */
export interface Goal {
  track: RewardTrack;
  /** `null` means "just maximise this track", with no finish line. */
  target: number | null;
  unitLabel: string;
  current: number;
  deadline: ISODate | null;
  purpose: string;
  /** Units earned per month at the current rate of spending. */
  pacePerMonth: number;
  /** When the target is reached if nothing changes. */
  projectedAt: ISODate | null;
  /** The single change that most improves the arrival date. */
  fix?: {
    action: string;
    pacePerMonth: number;
    projectedAt: ISODate;
  };
}

/* ------------------------------------------------------ planned spend --- */

export type PlannedKind = "event" | "purchase";

export interface PlannedItem {
  id: string;
  kind: PlannedKind;
  label: string;
  startDate: ISODate;
  /** Events span days; purchases land on one. */
  endDate?: ISODate;
  amount: number;
  categories: string[];
  note?: string;
}

/** User-entered planned spending before the backend assigns its canonical ID. */
export type PlannedItemDraft = Omit<PlannedItem, "id">;

/* --------------------------------------------------------- track record --- */

export type AdviceOutcome = "open" | "acted" | "dismissed" | "expired";

export interface AdviceRecord {
  id: string;
  outcome: AdviceOutcome;
  pushedAt: ISODate;
  resolvedAt?: ISODate;
  headline: string;
  card?: CardRef;
  predicted: number;
  /** Only known once the period closed and the transactions landed. */
  actual?: number;
  window: string;
  /** Why prediction and reality diverged. Shown verbatim; never rounded away. */
  gapReason?: string;
}

export interface TrackRecord {
  taken: number;
  offered: number;
  earned: number;
  missed: number;
  accuracyNote: string;
  records: AdviceRecord[];
}

/* ------------------------------------------------------------- wallet ----- */

export interface ParsedRule {
  /** Stable identity assigned by Card Intelligence; absent on legacy snapshots. */
  id?: string;
  categoryLabel: string;
  /** Display string only. Never calculate from this — use valuePerDollar. */
  rate: string;
  /** Always spend, in the card's currency. A reward cap is converted first. */
  cap: number | null;
  cycleLabel: string;
  /** Nominal currency returned per dollar spent, priced by programme. */
  valuePerDollar?: number;
  rewardType?: "cashback" | "points" | "miles";
  rateValue?: number;
  rateUnit?: "percent" | "points_per_dollar" | "miles_per_dollar";
  capType?: "spend" | "reward" | null;
  /** The figure the document itself stated, before conversion to spend. */
  capValue?: number | null;
  minSpend?: number | null;
  rewardCurrency?: string | null;
  /** What one point or mile of this programme is assumed to be worth. */
  rewardUnitValue?: number;
  rewardUnitValueSource?: string;
  currency?: string;
  notes?: string | null;

  /** Everything that narrows this rate, already phrased for display. */
  restrictions?: string[];
  /** Merchant category codes this rate applies to. Ranges like "3000-3299" allowed. */
  mccCodes?: string[];
  merchants?: string[];
  channels?: string[];
  exclusions?: string[];
  conditions?: { kind: string; description: string; amount?: number | null }[];
  tier?: "base" | "bonus" | "promotional";
  requiresSelection?: boolean;
  selectableCategories?: string[];
  stacksWithBase?: boolean;
  /** Set when the card pays in more than one currency and the holder picks. */
  hasRewardChoice?: boolean;
  alternativeRewards?: {
    rewardType: string;
    rewardCurrency?: string | null;
    rateValue: number;
    rateUnit: string;
    valuePerDollar?: number;
  }[];
}

export interface CardCharacteristics {
  issuer?: string;
  currency?: string;
  rewardCurrency?: string;
  annualFee?: number;
  feeWaiverSpend?: number;
  minIncome?: number;
  foreignTxFeePct?: number;
}

export type ParseStatus = "parsed" | "failed" | "stale";

export interface CardDetail {
  /** Persisted wallet document ID, used for user-scoped removal. */
  cardId?: string;
  /** Authoritative wallet document ID, distinct from the global card ID. */
  walletId?: string;
  /** Legacy Firestore document ID retained in older snapshots. */
  id?: string;
  /** Plaid credit account whose transactions were made on this card. */
  accountId?: string | null;
  name: string;
  last4: string;
  network: string;
  annualFee: number;
  track: RewardTrack;
  rules: ParsedRule[];
  source: { label: string; locator: string; retrievedAt: ISODate };
  recheckCadence: string;
  nextRecheckAt: ISODate;
  parseStatus: ParseStatus;
  parseNote?: string;
  parseConfidence?: number;
  failureReason?: string | null;
  characteristics?: CardCharacteristics;
  termsUrl?: string | null;
  documentSummary?: string | null;
  currency?: string;
  /** Structures the agent saw but could not model, plus anything inconsistent. */
  unresolved?: string[];
}

/* ------------------------------------------------------------ catalog ----- */

export interface CatalogCard {
  name: string;
  network: string;
  headlineRate: string;
  annualFee: number;
  track: RewardTrack;
  held: boolean;
  /** Nominal dollars per quarter against this user's real spending, net of fee. */
  deltaVsWallet: number;
  deltaNote?: string;
  tags: string[];
}

/* ----------------------------------------------------------- activity ----- */

export interface AgentLogEntry {
  id: string;
  agent: AgentId;
  status: AgentStatus;
  startedAt: ISODate;
  durationMs: number;
  summary: string;
  detail?: string;
  /** Firestore collection this run wrote to. Agents never call each other. */
  writes: string;
  reads?: string[];
  retryable?: boolean;
}

export interface CollectionLink {
  collection: string;
  writtenBy: AgentId;
  readBy: AgentId[];
}

/* ----------------------------------------------------------- snapshot ----- */

export interface Snapshot {
  readModelVersion?: number;
  generatedAt: ISODate;
  period: Period;
  totals: Totals;
  agents: AgentRun[];
  recommendations: Recommendation[];
  categories: CategoryLeak[];
  cards: CardCap[];
  tracks: TrackValuation[];
  /** `null` means the user has stated no preference and the agent picks one. */
  trackPreference: RewardTrack | null;
  recommendedTrack: RewardTrack;
  trackRationale: string;

  forecast: Forecast;
  /** `null` until the user sets one. The dashboard handles that state. */
  goal: Goal | null;
  planned: PlannedItem[];
  trackRecord: TrackRecord;
  wallet: CardDetail[];
  catalog: CatalogCard[];
  activity: AgentLogEntry[];
  collections: CollectionLink[];
}
