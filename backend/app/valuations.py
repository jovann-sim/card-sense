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
    # US transferable bank currencies. These are the ones that matter, because
    # every major US card earns into one of them.
    "membership rewards": (0.020, "Placeholder: ~2.0 cents via airline transfer partners. Confirm."),
    "ultimate rewards": (0.0205, "Placeholder: ~2.05 cents via transfer partners. Confirm."),
    "thankyou points": (0.018, "Placeholder: ~1.8 cents via transfer partners. Confirm."),
    "venture miles": (0.0185, "Placeholder: Capital One miles, ~1.85 cents via transfers. Confirm."),
    "capital one miles": (0.0185, "Placeholder: ~1.85 cents via transfer partners. Confirm."),
    "bilt points": (0.0205, "Placeholder: ~2.05 cents via transfer partners. Confirm."),

    # US airline and hotel programmes
    "skymiles": (0.012, "Placeholder: Delta, ~1.2 cents. Confirm."),
    "aadvantage": (0.014, "Placeholder: American, ~1.4 cents. Confirm."),
    "mileageplus": (0.013, "Placeholder: United, ~1.3 cents. Confirm."),
    "rapid rewards": (0.014, "Placeholder: Southwest, ~1.4 cents and revenue-based. Confirm."),
    "alaska mileage plan": (0.015, "Placeholder: ~1.5 cents. Confirm."),
    "jetblue trueblue": (0.013, "Placeholder: ~1.3 cents. Confirm."),
    "marriott bonvoy": (0.0075, "Placeholder: ~0.75 cents. Confirm."),
    "hilton honors": (0.005, "Placeholder: ~0.5 cents. Confirm."),
    "world of hyatt": (0.017, "Placeholder: ~1.7 cents, the strongest hotel currency. Confirm."),
    "ihg one rewards": (0.005, "Placeholder: ~0.5 cents. Confirm."),

    # Cash-equivalent programmes. Redeemable at face value, so no discount.
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
