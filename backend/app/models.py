from datetime import date, datetime
from pydantic import BaseModel, Field
from typing import Any, Literal

RewardTrack = Literal["points", "cashback", "miles"]
AdviceOutcome = Literal["open", "acted", "dismissed", "expired"]

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

class SyncIn(BaseModel):
    userId: str = "demo-user"
    itemId: str | None = None
    cursor: str | None = None

class AgentLog(BaseModel):
    id: str
    agent: str
    status: str
    startedAt: str
    durationMs: int
    summary: str
    detail: str | None = None
    writes: str
    reads: list[str] = []
    retryable: bool = False
