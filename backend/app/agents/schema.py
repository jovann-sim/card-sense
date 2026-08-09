from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Nominal dollar value of one unit of each reward currency. Kept here rather
# than in strategy.py so extraction can pre-compute valuePerDollar without the
# two modules importing each other.
VALUATIONS = {"cashback": 1.0, "points": 0.01, "miles": 0.013}

RewardType = Literal["cashback", "points", "miles"]
RateUnit = Literal["percent", "points_per_dollar", "miles_per_dollar"]
CapType = Literal["spend", "reward"]
Cycle = Literal["per month", "per quarter", "per year", "per statement", "no cap"]


class ExtractedRule(BaseModel):
    """One earn rate, expressed so the strategy agent never has to parse prose."""

    categoryLabel: str = Field(description="Spending category, e.g. Dining, Groceries, Everything else")
    rewardType: RewardType
    rateValue: float = Field(ge=0, description="4 for 4% cashback; 1.4 for 1.4 miles per dollar")
    rateUnit: RateUnit
    cap: float | None = Field(default=None, description="Cap amount, null if uncapped")
    capType: CapType | None = Field(default=None, description="Whether cap limits spend or reward earned")
    cycleLabel: Cycle = "no cap"
    minSpend: float | None = Field(default=None, description="Minimum spend in the cycle to qualify")
    notes: str | None = Field(default=None, description="One short caveat, only if materially conditional")


class ExtractedCharacteristics(BaseModel):
    """Card-level facts that shape whether a card is worth holding at all."""

    issuer: str | None = None
    currency: str | None = Field(default=None, description="ISO code of the card's billing currency, e.g. SGD, USD")
    rewardCurrency: str | None = Field(default=None, description="Name of the points/miles programme, if any")
    annualFee: float | None = Field(default=None, ge=0)
    feeWaiverSpend: float | None = Field(default=None, ge=0, description="Annual spend that waives the fee")
    minIncome: float | None = Field(default=None, ge=0)
    foreignTxFeePct: float | None = Field(default=None, ge=0)


class ExtractionResult(BaseModel):
    """What the model is asked to return. Nothing outside this shape is accepted."""

    rules: list[ExtractedRule] = Field(default_factory=list)
    characteristics: ExtractedCharacteristics = Field(default_factory=ExtractedCharacteristics)
    confidence: float = Field(default=0.0, ge=0, le=1, description="0 if the document did not state rates plainly")
    documentSummary: str | None = Field(default=None, description="One sentence on what this document is")


def value_per_dollar(rule: ExtractedRule | dict) -> float:
    """Nominal dollars returned per dollar spent — the only number strategy needs.

    A percentage is already a fraction of the dollar. A per-dollar earn rate has
    to be priced through the reward currency: 1.4 miles per dollar at $0.013 a
    mile returns $0.0182 per dollar spent.
    """
    data = rule if isinstance(rule, dict) else rule.model_dump()
    rate = float(data.get("rateValue") or 0)
    unit = data.get("rateUnit")
    reward = data.get("rewardType", "cashback")

    if unit == "percent":
        return round(rate / 100, 6)
    return round(rate * VALUATIONS.get(reward, 0.01), 6)


def spend_cap(rule: ExtractedRule | dict) -> float | None:
    """The cap expressed as spend, whichever way the issuer worded it.

    Issuers cap either the spend that earns the bonus rate ("5% on the first
    $600 a month") or the reward itself ("up to $60 cashback a month"). The
    optimiser allocates spend, so a reward cap has to be divided back through
    the earn rate before it can be compared with anything.
    """
    data = rule if isinstance(rule, dict) else rule.model_dump()
    cap = data.get("cap")
    if cap is None:
        return None
    cap = float(cap)
    if data.get("capType") != "reward":
        return cap

    rate = float(data.get("rateValue") or 0)
    if rate <= 0:
        return None
    if data.get("rateUnit") == "percent":
        return round(cap / (rate / 100), 2)
    return round(cap / rate, 2)


def display_rate(rule: ExtractedRule | dict) -> str:
    """Human-facing string. The UI shows this; nothing calculates from it."""
    data = rule if isinstance(rule, dict) else rule.model_dump()
    rate, unit = data.get("rateValue"), data.get("rateUnit")
    if rate is None:
        return "—"
    trimmed = f"{float(rate):g}"
    if unit == "percent":
        return f"{trimmed}% cash back"
    if unit == "miles_per_dollar":
        return f"{trimmed} mpd"
    return f"{trimmed}× points"


EXTRACTION_PROMPT = """You are reading a credit card's published terms to extract its reward structure.

Extract every distinct earn rate the document states. For each one:
- rateValue and rateUnit carry the number. Use `percent` for cashback ("4% cash back" -> rateValue 4, rateUnit percent). Use `miles_per_dollar` for air miles ("1.4 mpd", "1.4 miles per S$1" -> rateValue 1.4, rateUnit miles_per_dollar). Use `points_per_dollar` for points ("4X points", "10 points per dollar" -> rateValue 4 or 10, rateUnit points_per_dollar).
- cap is the numeric limit and capType says what it limits. "5% cashback on up to $600 spend monthly" -> cap 600, capType spend, cycleLabel "per month". "Up to $60 cashback monthly" -> cap 60, capType reward, cycleLabel "per month".
- minSpend is any minimum the cardholder must spend in the cycle to earn the bonus rate.
- Always include the base or fallback rate that applies to everything else, with categoryLabel "Everything else".

Rules:
- Extract only what the document states. Never infer, average, or complete a rate from general knowledge of this card.
- If the document does not plainly state earn rates, return an empty rules list and confidence 0.
- confidence reflects how plainly the rates were stated: 0.9+ when rates and caps are explicit, 0.5 or below when you had to interpret marketing copy, 0 when absent.
- Promotional or time-limited rates should be omitted unless the document gives no ongoing rate.
"""
