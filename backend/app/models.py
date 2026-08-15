from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

RewardTrack = Literal["points", "cashback", "miles"]
AdviceOutcome = Literal["open", "acted", "dismissed", "expired"]
AgentStatus = Literal["not-run", "ok", "degraded", "running"]
ForecastQuality = Literal["none", "limited", "good"]


class PlannedItemIn(BaseModel):
    kind: Literal["event", "purchase"]
    label: str
    startDate: date
    endDate: date | None = None
    amount: float = Field(gt=0)
    categories: list[str]
    note: str | None = None


class GoalIn(BaseModel):
    track: RewardTrack
    target: float | None = Field(default=None, ge=0)
    unitLabel: str
    current: float = Field(default=0, ge=0)
    deadline: date | None = None
    purpose: str = ""


class AdviceResolveIn(BaseModel):
    outcome: AdviceOutcome


class CardIn(BaseModel):
    name: str
    last4: str = Field(min_length=4, max_length=4)
    network: str
    annualFee: float = Field(default=0, ge=0)
    track: RewardTrack
    accountId: str | None = None
    termsText: str | None = None
    termsUrl: str | None = None
    rules: list[dict[str, Any]] | None = None


class RunIn(BaseModel):
    request: str = "Run the CardSense autonomous spending analysis."
    # Which engine executes the pipeline. The ADK graph and the built-in
    # orchestrator write the same read model, so this is not observable to a
    # user — it exists so one can be proven against the other.
    engine: Literal["orchestrator", "adk"] | None = None


class LinkTokenIn(BaseModel):
    userId: str = "demo-user"


class ExchangeTokenIn(BaseModel):
    publicToken: str
    userId: str = "demo-user"
    institutionId: str | None = None
    institutionName: str | None = None


class SyncIn(BaseModel):
    userId: str = "demo-user"
    itemId: str | None = None
    cursor: str | None = None


# The following models deliberately mirror web/lib/types.ts.  The API owns this
# boundary so components can consume a Snapshot without defensive parsing.
class AgentRun(BaseModel):
    id: Literal["ingestion", "forecast", "card-intelligence", "strategy", "advisory"]
    label: str
    status: AgentStatus
    lastRunAt: str | None = None
    note: str | None = None


class TimelineEntry(BaseModel):
    date: str
    kind: Literal["event", "purchase", "cap", "deadline", "agent", "reset"]
    title: str
    detail: str | None = None
    action: str | None = None
    amount: float | None = None


class ForecastMonth(BaseModel):
    month: str
    label: str
    days: int
    variable: float
    recurring: float
    planned: float
    total: float
    cumulative: float
    cumulativeConfidence: float


class ForecastCategory(BaseModel):
    category: str
    mcc: str
    variable: float
    recurring: float
    planned: float
    projected: float
    monthly: float
    share: float


class RecurringStream(BaseModel):
    merchant: str
    category: str | None = None
    cadence: Literal["weekly", "fortnightly", "semi-monthly", "monthly", "quarterly", "yearly"]
    amount: float
    monthlyAmount: float
    occurrences: int
    nextDue: str
    confidence: Literal["low", "medium", "high"]
    # A bill is a standing arrangement and is projected by date. A habit is
    # regular spending at one merchant, counted as a rate instead.
    kind: Literal["bill", "habit"] = "bill"


class ForecastOutput(BaseModel):
    horizonDays: int
    horizonMonths: int = 1
    baselineSpend: float
    variableSpend: float = 0.0
    recurringSpend: float = 0.0
    plannedSpend: float
    projectedSpend: float
    historyDays: int
    quality: ForecastQuality
    confidence: float
    # How far the history actually supports projecting, and whether the chosen
    # horizon went past it. Stated so the interface can distinguish a forecast
    # from an extrapolation instead of presenting both with equal certainty.
    reliableMonths: int = 0
    extrapolated: bool = False
    basis: str
    months: list[ForecastMonth] = []
    categories: list[ForecastCategory] = []
    recurring: list[RecurringStream] = []
    timeline: list[TimelineEntry]
    doNothingCost: float
    doNothingWindow: str


class Snapshot(BaseModel):
    readModelVersion: int = 5
    generatedAt: str
    period: dict[str, Any]
    totals: dict[str, float]
    agents: list[AgentRun]
    recommendations: list[dict[str, Any]]
    categories: list[dict[str, Any]]
    cards: list[dict[str, Any]]
    tracks: list[dict[str, Any]]
    trackPreference: RewardTrack | None = None
    recommendedTrack: RewardTrack
    trackRationale: str
    forecast: ForecastOutput
    goal: dict[str, Any] | None = None
    planned: list[dict[str, Any]]
    trackRecord: dict[str, Any]
    wallet: list[dict[str, Any]]
    catalog: list[dict[str, Any]]
    activity: list[dict[str, Any]]
    collections: list[dict[str, Any]]


class RunResponse(BaseModel):
    runId: str
    snapshot: Snapshot


class CardResponse(BaseModel):
    card: dict[str, Any]
    snapshot: Snapshot
