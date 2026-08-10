from __future__ import annotations

import re

# Everything is priced in US dollars unless a card's own terms are denominated
# elsewhere, in which case the reward stays in that currency and is labelled
# rather than converted — a live FX rate is not something this system should be
# silently inventing.
BASE_CURRENCY = "USD"


# Value of ONE unit of each reward currency, in SGD.
#
# These are assumptions, not facts. A mile is worth what you redeem it for, and
# that varies by cabin, route and season. Every figure below is a placeholder
# carrying its own reasoning so the interface can show the assumption next to
# the number it produced. Confirm them against real redemptions before the
# numbers are presented as advice.
REWARD_UNIT_VALUES: dict[str, tuple[float, str]] = {
    # Figures are dollars per unit, checked August 2026 against Upgraded Points
    # and CardRatings. Where the two disagreed the midpoint is used and both
    # numbers are named, because the spread is the honest uncertainty: a mile is
    # worth what you redeem it for, and these are averages over redemptions
    # people actually make.
    #
    # Transferable bank currencies — what most US cards earn into.
    "membership rewards": (0.021, "Aug 2026: Upgraded Points 2.2c, CardRatings 2.0c. Midpoint."),
    "ultimate rewards": (0.020, "Aug 2026: Upgraded Points 2.0c, CardRatings 2.05c. Midpoint."),
    "thankyou points": (0.0165, "Aug 2026: Upgraded Points 1.6c, CardRatings 1.7c. Midpoint."),
    "venture miles": (0.018, "Aug 2026: both sources 1.8c."),
    "capital one miles": (0.018, "Aug 2026: both sources 1.8c."),
    "bilt points": (0.020, "Aug 2026: Upgraded Points 2.0c."),

    # Airline programmes
    "aadvantage": (0.014, "Aug 2026: Upgraded Points 1.4c."),
    "skymiles": (0.012, "Aug 2026: Upgraded Points 1.2c."),
    "mileageplus": (0.012, "Aug 2026: Upgraded Points 1.2c."),
    "rapid rewards": (0.013, "Aug 2026: Upgraded Points 1.3c. Revenue-based, so unusually stable."),
    "atmos rewards": (0.016, "Aug 2026: Upgraded Points 1.6c. Alaska's programme, renamed from Mileage Plan."),
    "alaska mileage plan": (0.016, "Aug 2026: 1.6c. Now branded Atmos Rewards."),
    "jetblue trueblue": (0.013, "Aug 2026: Upgraded Points 1.3c."),

    # Hotel programmes. Worth far less per point, and the spread between them
    # is wide enough that treating them alike would be a real error.
    "world of hyatt": (0.014, "Aug 2026: Upgraded Points 1.4c. The strongest hotel currency."),
    "marriott bonvoy": (0.007, "Aug 2026: Upgraded Points 0.7c."),
    "hilton honors": (0.005, "Aug 2026: Upgraded Points 0.5c."),
    "ihg one rewards": (0.005, "Aug 2026: Upgraded Points 0.5c."),

    # Cash-equivalent programmes redeem at face value, so no discount applies.
    "reward dollars": (1.0, "Amex Reward Dollars redeem as a statement credit at face value."),
    "cash rewards": (1.0, "Redeems as cash or statement credit at face value."),
    "discover cashback bonus": (1.0, "Redeems as cash at face value."),

    # Retained for cards denominated outside the US.
    "krisflyer miles": (0.014, "Placeholder: ~1.4 US cents. Confirm."),
    "asia miles": (0.013, "Placeholder: ~1.3 US cents. Confirm."),
    "avios": (0.013, "Placeholder: ~1.3 US cents. Confirm."),
}

# Used when the document names no programme, or names one we do not price.
DEFAULT_UNIT_VALUES: dict[str, tuple[float, str]] = {
    "cashback": (1.0, "Cash back is already denominated in dollars. No conversion applied."),
    "miles": (0.013, "Placeholder default for an unrecognised airline programme. Confirm."),
    "points": (0.012, "Placeholder default for an unrecognised bank points programme. Confirm."),
}

# Kept for callers that predate per-programme pricing.
VALUATIONS = {name: value for name, (value, _) in DEFAULT_UNIT_VALUES.items()}


def _normalise(name: str | None) -> str:
    if not name:
        return ""
    cleaned = re.sub(r"[^a-z0-9$ ]+", " ", name.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def unit_value(reward_currency: str | None, reward_type: str = "points") -> tuple[float, str]:
    """What one point or mile of this programme is worth, and why.

    Falls back to a per-type default rather than refusing, because a card whose
    programme we do not recognise should still be comparable — just with the
    assumption stated plainly alongside it.
    """
    key = _normalise(reward_currency)
    if key in REWARD_UNIT_VALUES:
        return REWARD_UNIT_VALUES[key]

    # "HSBC Reward points" should still match "reward points".
    for known, priced in REWARD_UNIT_VALUES.items():
        if known and known in key:
            return priced

    fallback = DEFAULT_UNIT_VALUES.get(reward_type) or DEFAULT_UNIT_VALUES["points"]
    if key:
        return fallback[0], f"{fallback[1]} Programme named as “{reward_currency}”."
    return fallback


# Two reward options on the same rule describe one reward paid two ways, so
# they should price to roughly the same figure. A wide gap means either the
# extraction misread a conversion or a programme is mispriced — both worth
# saying out loud rather than quietly feeding into a recommendation.
DIVERGENCE_TOLERANCE = 0.35


def divergence(values: list[float]) -> float:
    """How far apart the priced options are, as a fraction of the largest."""
    priced = [v for v in values if v > 0]
    if len(priced) < 2:
        return 0.0
    return (max(priced) - min(priced)) / max(priced)
