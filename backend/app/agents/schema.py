from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..valuations import BASE_CURRENCY, VALUATIONS, unit_value  # noqa: F401

RewardType = Literal["cashback", "points", "miles"]
RateUnit = Literal["percent", "points_per_dollar", "miles_per_dollar"]
CapType = Literal["spend", "reward"]
Cycle = Literal["per month", "per quarter", "per year", "per statement", "no cap"]
Tier = Literal["base", "bonus", "promotional"]
Channel = Literal["online", "in_store", "contactless", "foreign_currency", "any"]
ConditionKind = Literal[
    "minimum_spend",
    "enrolment",
    "category_selection",
    "banking_relationship",
    "new_customer",
    "promotional_period",
    "spend_elsewhere",
    "other",
]


class RewardOption(BaseModel):
    """One way of being paid for the same spending.

    Cards like the DBS yuu let the holder choose between a loyalty currency and
    cash back. Both are real rates on the same rule, so both are recorded and
    the card's own stated track decides which one is priced.
    """

    rewardType: RewardType
    rewardCurrency: str | None = Field(default=None, description="Programme name, e.g. yuu Points, UNI$, KrisFlyer miles")
    rateValue: float = Field(ge=0, description="4 for 4%; 1.4 for 1.4 miles per dollar; 10 for 10X points")
    rateUnit: RateUnit


class Condition(BaseModel):
    """Something that must be true before this rate applies at all."""

    kind: ConditionKind
    description: str = Field(description="One clause, quoted plainly from the document")
    amount: float | None = Field(default=None, description="Threshold amount where the condition states one")
    cycleLabel: Cycle = "no cap"


class ExtractedRule(BaseModel):
    """One earn rate, with everything that qualifies it."""

    categoryLabel: str = Field(description="Human name, e.g. Dining, Groceries, Everything else")
    tier: Tier = Field(default="bonus", description="base is the everyday rate; bonus is the elevated one")

    # Scope. A rate that only applies at named merchants is not a category rate,
    # and treating it as one overstates what the card will actually return.
    mccCodes: list[str] = Field(default_factory=list, description="Merchant category codes the document names, or the standard codes for the category it describes")
    merchants: list[str] = Field(default_factory=list, description="Specific named merchants or brands, if the rate is limited to them")
    channels: list[Channel] = Field(default_factory=list, description="Payment channels the rate is limited to")
    exclusions: list[str] = Field(default_factory=list, description="Spending the document explicitly excludes")

    rewards: list[RewardOption] = Field(default_factory=list, description="Every reward currency this rate can be paid in. More than one means the holder chooses.")

    cap: float | None = Field(default=None, description="Cap amount, null if uncapped")
    capType: CapType | None = None
    cycleLabel: Cycle = "no cap"
    minSpend: float | None = Field(default=None, description="Minimum spend in the cycle to qualify")

    conditions: list[Condition] = Field(default_factory=list)
    requiresSelection: bool = Field(default=False, description="True when the holder must nominate this category themselves")
    selectableCategories: list[str] = Field(default_factory=list, description="The menu they choose from, if the document lists it")
    stacksWithBase: bool = Field(default=False, description="True when this rate is earned on top of the base rate rather than instead of it")

    notes: str | None = Field(default=None, description="One short caveat that does not fit the fields above")


class ExtractedCharacteristics(BaseModel):
    """Card-level facts that shape whether a card is worth holding at all."""

    issuer: str | None = None
    currency: str | None = Field(default=None, description="ISO code of the card's billing currency, e.g. SGD, USD")
    rewardCurrency: str | None = Field(default=None, description="Primary points or miles programme, if any")
    annualFee: float | None = Field(default=None, ge=0)
    feeWaiverSpend: float | None = Field(default=None, ge=0)
    minIncome: float | None = Field(default=None, ge=0)
    foreignTxFeePct: float | None = Field(default=None, ge=0)
    rewardExpiryMonths: float | None = Field(default=None, ge=0)


class ExtractionResult(BaseModel):
    rules: list[ExtractedRule] = Field(default_factory=list)
    characteristics: ExtractedCharacteristics = Field(default_factory=ExtractedCharacteristics)
    confidence: float = Field(default=0.0, ge=0, le=1)
    documentSummary: str | None = None
    unresolved: list[str] = Field(default_factory=list, description="Structures present in the document that could not be expressed in these fields")


# ------------------------------------------------------------------ pricing --

def value_per_dollar(rule: ExtractedRule | dict, reward_currency: str | None = None) -> float:
    """Nominal currency returned per dollar spent — the only number strategy needs."""
    data = rule if isinstance(rule, dict) else rule.model_dump()
    rate = float(data.get("rateValue") or 0)
    unit = data.get("rateUnit")
    reward = data.get("rewardType", "cashback")

    if unit == "percent":
        return round(rate / 100, 6)
    if reward == "cashback":
        return round(rate, 6)

    priced, _ = unit_value(reward_currency or data.get("rewardCurrency"), reward)
    return round(rate * priced, 6)


def option_value(option: RewardOption | dict) -> float:
    data = option if isinstance(option, dict) else option.model_dump()
    return value_per_dollar(data, data.get("rewardCurrency"))


def choose_reward(rewards, preferred_track: str | None) -> dict | None:
    """Pick which reward currency this card is actually being paid in.

    Where a card offers a choice, the holder's stated track decides. Falling
    back to the most valuable option would quietly assume they redeem for
    whatever prices highest, which is not the same as what they will do.
    """
    options = [r if isinstance(r, dict) else r.model_dump() for r in rewards or []]
    if not options:
        return None
    if preferred_track:
        for option in options:
            if option.get("rewardType") == preferred_track:
                return option
    return max(options, key=option_value)


def spend_cap(rule: ExtractedRule | dict) -> float | None:
    """The cap expressed as spend, whichever way the issuer worded it."""
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


EXTRACTION_PROMPT = """You are reading a credit card's published terms to extract its complete reward structure.

Real cards are more conditional than a single rate per category. Capture the structure faithfully.

RATES
- rewards lists every currency this rate can be paid in. If the card lets the holder choose — for example yuu Points or cash back — record BOTH as separate entries in rewards, not two rules.
- rateValue and rateUnit carry the number. "4% cash back" -> 4 + percent. "1.4 miles per S$1" -> 1.4 + miles_per_dollar. "10X points" or "10 UNI$ per S$5" -> convert to per-dollar and use points_per_dollar.
- tier: "base" is the everyday rate that applies to all spending; "bonus" is an elevated rate on some subset; "promotional" is time-limited.
- stacksWithBase: true when the document says the bonus is earned in addition to the base rate.

SCOPE — this is what stops a rate being overstated
- mccCodes: the merchant category codes the document names. If it describes a category in words without codes, supply the standard MCCs for it (dining 5812/5813/5814, groceries 5411/5422/5451, petrol 5541/5542, airlines 3000-3299/4511, hotels 3500-3999/7011, transit 4111/4121, streaming 5815/5816/5817/5818).
- merchants: fill this ONLY when the rate is limited to named brands or partners. A rate at Cold Storage, Giant and Guardian is a merchant rate, not a groceries rate.
- channels: online, in_store, contactless, foreign_currency — only where the document restricts it.
- exclusions: spending the document explicitly excludes from earning.

CONDITIONS — record every qualifier as its own entry
- minimum_spend, enrolment, category_selection, banking_relationship (holding a linked savings or salary account), new_customer, promotional_period, spend_elsewhere.
- requiresSelection is true when the holder must nominate the bonus category themselves, as on cards where you pick your own bonus categories. List the menu in selectableCategories if the document gives it.

CAPS
- cap is the numeric limit and capType says what it limits. "5% on up to $600 spend monthly" -> cap 600, capType spend. "Up to $60 cash back monthly" -> cap 60, capType reward.

RULES OF ENGAGEMENT
- Extract only what the document states. Never infer a rate, cap or condition from general knowledge of this card. The one exception is supplying standard MCC codes for a category the document describes in words.
- Always include the base rate that applies to everything else, with categoryLabel "Everything else" and tier "base".
- If the document does not plainly state earn rates, return an empty rules list and confidence 0.
- confidence: 0.9+ when rates, caps and conditions are explicit; 0.5 or below when you had to interpret marketing copy; 0 when absent.
- unresolved: list any reward structure you could see in the document but could not express in these fields. An honest gap is more useful than a wrong value.
"""
