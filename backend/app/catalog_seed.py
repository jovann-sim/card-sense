from __future__ import annotations

from .mcc import codes_for

# Reference rules for cards the user does not hold.
#
# The simulator can only answer "would another card do better" if the other
# cards are described in the same terms as the held ones — MCC lists and a
# value per dollar, not a headline sentence. Card intelligence produces exactly
# that from an issuer's document; this is the same shape, hand-written, so the
# comparison has something to run against before every catalog card has been
# read. Anything read from real terms overwrites it.
#
# Rates are the long-standing public offers. Values per dollar are priced
# through valuations.py, so they move when those do rather than drifting apart.
CATALOG: list[dict] = [
    {
        "id": "sapphire-preferred",
        "name": "Chase Sapphire Preferred",
        "network": "Visa",
        "annualFee": 95,
        "track": "points",
        "programme": "ultimate rewards",
        "headlineRate": "5x travel booked through Chase, 3x dining",
        "welcomeBonus": {"award": 60000, "unit": "points", "minSpend": 4000, "windowDays": 90},
        "rates": [
            ("Travel booked through Chase", "travel", 5.0),
            ("Dining", "dining", 3.0),
            ("Streaming", "streaming", 3.0),
            ("Groceries", "groceries", 3.0),
            ("Travel", "travel", 2.0),
            ("Everything else", None, 1.0),
        ],
    },
    {
        "id": "venture-x",
        "name": "Capital One Venture X",
        "network": "Visa",
        "annualFee": 395,
        "track": "miles",
        "programme": "venture miles",
        "headlineRate": "10x hotels booked through Capital One, 2x everything",
        "welcomeBonus": {"award": 75000, "unit": "miles", "minSpend": 4000, "windowDays": 90},
        "rates": [
            ("Hotels booked through Capital One", "hotels", 10.0),
            ("Air travel booked through Capital One", "air travel", 5.0),
            ("Everything else", None, 2.0),
        ],
    },
    {
        "id": "amex-gold",
        "name": "American Express Gold",
        "network": "Amex",
        "annualFee": 325,
        "track": "points",
        "programme": "membership rewards",
        "headlineRate": "4x dining and US supermarkets",
        "welcomeBonus": {"award": 60000, "unit": "points", "minSpend": 6000, "windowDays": 180},
        "rates": [
            ("Dining", "dining", 4.0),
            ("U.S. Supermarkets", "groceries", 4.0),
            ("Air travel", "air travel", 3.0),
            ("Everything else", None, 1.0),
        ],
    },
    {
        "id": "citi-custom-cash",
        "name": "Citi Custom Cash",
        "network": "Mastercard",
        "annualFee": 0,
        "track": "cashback",
        "programme": "thankyou points",
        "headlineRate": "5% on your top category each cycle, capped",
        "welcomeBonus": {"award": 20000, "unit": "points", "minSpend": 1500, "windowDays": 180},
        "rates": [
            # Capped and self-selecting, which is why the cap matters more than
            # the rate: 5% on $500 a month is worth less than 2% uncapped.
            # The 5% follows whichever category you spend most in that cycle,
            # which no MCC list can express. Marked conditional so it is
            # reported as unverified rather than silently counted as zero.
            ("Top eligible category", None, 5.0,
             {"capSpend": 500, "cycleLabel": "per month", "requiresSelection": True}),
            ("Everything else", None, 1.0),
        ],
    },
    {
        "id": "wells-active-cash",
        "name": "Wells Fargo Active Cash",
        "network": "Visa",
        "annualFee": 0,
        "track": "cashback",
        "programme": None,
        "headlineRate": "2% on everything",
        "welcomeBonus": {"award": 200, "unit": "cashback", "minSpend": 500, "windowDays": 90},
        "rates": [("Everything else", None, 2.0)],
    },
]


def _value_per_dollar(track: str, programme: str | None, rate: float) -> float:
    """Price a multiplier through the same valuation table the wallet uses.

    The programme matters more than the track: an Amex point is worth 2.1 cents
    and a generic "points" fallback prices it at 1.2, which would have made
    every transferable-currency card look about forty percent worse than it is.
    An unknown programme raises rather than quietly falling back, because a
    silent mispricing here changes which card the product recommends.
    """
    from .valuations import REWARD_UNIT_VALUES

    if track == "cashback":
        return round(rate / 100, 6)
    if programme not in REWARD_UNIT_VALUES:
        raise KeyError(f"No valuation for reward programme {programme!r}")
    per_point = REWARD_UNIT_VALUES[programme][0]
    return round(rate * per_point, 6)


def rules_for(entry: dict) -> list[dict]:
    """Catalog rates in the same shape card intelligence emits."""
    rules = []
    for index, rate in enumerate(entry["rates"]):
        label, category, multiplier = rate[0], rate[1], rate[2]
        extra = rate[3] if len(rate) > 3 else {}
        rules.append({
            "id": f"{entry['id']}-{index}",
            "categoryLabel": label,
            "rate": f"{multiplier:g}% cash back" if entry["track"] == "cashback" else f"{multiplier:g}x",
            "valuePerDollar": _value_per_dollar(entry["track"], entry.get("programme"), multiplier),
            "mccCodes": codes_for(category) if category else [],
            "tier": "base" if category is None and multiplier <= 2 else "bonus",
            "source": "catalog-reference",
            **extra,
        })
    return rules


def seed(store, uid: str) -> int:
    """Write the reference catalog, leaving anything already read from terms."""
    written = 0
    for entry in CATALOG:
        existing = store.get_subdoc(uid, "catalog", entry["id"]) or {}
        # A card whose real terms have been read outranks this table.
        if existing.get("rulesSource") == "card-intelligence":
            continue
        store.set_subdoc(uid, "catalog", entry["id"], {
            "id": entry["id"],
            "name": entry["name"],
            "network": entry["network"],
            "annualFee": entry["annualFee"],
            "track": entry["track"],
            "headlineRate": entry["headlineRate"],
            "welcomeBonus": entry["welcomeBonus"],
            "rules": rules_for(entry),
            "rulesSource": "catalog-reference",
            "held": False,
            "deltaVsWallet": 0,
            "tags": [entry["track"], *( ["no annual fee"] if not entry["annualFee"] else [])],
        })
        written += 1
    return written
