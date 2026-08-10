from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

RewardTrack = Literal["points", "cashback", "miles"]
AdviceOutcome = Literal["open", "acted", "dismissed", "expired"]
AgentStatus = Literal["ok", "degraded", "running"]
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
    lastRunAt: str
    note: str | None = None


class TimelineEntry(BaseModel):
    date: str
    kind: Literal["event", "purchase", "cap", "deadline", "agent", "reset"]
    title: str
    detail: str | None = None
    action: str | None = None
    amount: float | None = None


class ForecastOutput(BaseModel):
    horizonDays: int
    baselineSpend: float
    plannedSpend: float
    projectedSpend: float
    historyDays: int
    quality: ForecastQuality
    confidence: float
    basis: str
    timeline: list[TimelineEntry]
    doNothingCost: float
    doNothingWindow: str


class Snapshot(BaseModel):
    readModelVersion: int = 4
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
