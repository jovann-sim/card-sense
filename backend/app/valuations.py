from __future__ import annotations

import re

# Everything is priced in Singapore dollars unless a card's own terms are
# denominated elsewhere, in which case the reward stays in that currency and is
# labelled rather than converted — a live FX rate is not something this system
# should be silently inventing.
BASE_CURRENCY = "SGD"


# Value of ONE unit of each reward currency, in SGD.
#
# These are assumptions, not facts. A mile is worth what you redeem it for, and
# that varies by cabin, route and season. Every figure below is a placeholder
# carrying its own reasoning so the interface can show the assumption next to
# the number it produced. Confirm them against real redemptions before the
# numbers are presented as advice.
REWARD_UNIT_VALUES: dict[str, tuple[float, str]] = {
    # Airline currencies
    "krisflyer miles": (0.019, "Placeholder: ~1.9 SG cents, economy saver redemption. Confirm."),
    "asia miles": (0.018, "Placeholder: ~1.8 SG cents. Confirm."),
    "avios": (0.017, "Placeholder: ~1.7 SG cents. Confirm."),
    "enrich miles": (0.014, "Placeholder: ~1.4 SG cents. Confirm."),
    # Bank currencies that transfer out to airlines
    "membership rewards": (0.0095, "Placeholder: ~2 MR points per mile, so roughly half a mile's value. Confirm."),
    "thankyou points": (0.008, "Placeholder. Confirm against Citi transfer ratios."),
    "dbs points": (0.019, "Placeholder: 1 DBS point transfers to ~2 miles on most cards. Confirm."),
    "uni$": (0.019, "Placeholder: 1 UNI$ transfers to ~2 miles. Confirm."),
    "reward points": (0.0076, "Placeholder: ~2.5 HSBC points per mile. Confirm."),
    "ocbc$": (0.008, "Placeholder. Confirm against OCBC redemption tables."),
}

# Used when the document names no programme, or names one we do not price.
DEFAULT_UNIT_VALUES: dict[str, tuple[float, str]] = {
    "cashback": (1.0, "Cash back is already denominated in dollars. No conversion applied."),
    "miles": (0.017, "Placeholder default for an unrecognised airline programme. Confirm."),
    "points": (0.01, "Placeholder default for an unrecognised points programme. Confirm."),
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
