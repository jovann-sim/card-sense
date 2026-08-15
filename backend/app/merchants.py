from __future__ import annotations

import re

from .mcc import CATEGORY_MCC

# Domains to the merchant category code an acquirer would actually use.
#
# The extension knows a hostname and, at best, a site name from a meta tag. A
# card rule is written in MCCs. This is the join, and it is a table rather than
# a guess because a wrong code produces a confident wrong recommendation, which
# is worse than saying nothing.
#
# Only the second-level domain is matched, so amazon.co.uk and smile.amazon.com
# both resolve. Order does not matter; the longest matching key wins.
DOMAIN_MCC: dict[str, tuple[str, str]] = {
    # marketplaces and general retail
    "amazon": ("5399", "Online retail"),
    "ebay": ("5399", "Online retail"),
    "etsy": ("5399", "Online retail"),
    "walmart": ("5310", "Wholesale clubs"),
    "target": ("5310", "Wholesale clubs"),
    "costco": ("5300", "Wholesale clubs"),
    "samsclub": ("5300", "Wholesale clubs"),
    "aliexpress": ("5399", "Online retail"),
    "temu": ("5399", "Online retail"),
    "shein": ("5651", "Fashion"),

    # groceries and delivery
    "instacart": ("5411", "Groceries"),
    "wholefoodsmarket": ("5411", "Groceries"),
    "kroger": ("5411", "Groceries"),
    "safeway": ("5411", "Groceries"),
    "traderjoes": ("5411", "Groceries"),
    "freshdirect": ("5411", "Groceries"),

    # dining and food delivery
    "doordash": ("5814", "Dining"),
    "ubereats": ("5814", "Dining"),
    "grubhub": ("5814", "Dining"),
    "seamless": ("5814", "Dining"),
    "opentable": ("5812", "Dining"),
    "starbucks": ("5814", "Dining"),
    "chipotle": ("5814", "Dining"),
    "dominos": ("5814", "Dining"),

    # travel
    "expedia": ("4722", "Travel"),
    "booking": ("7011", "Hotels"),
    "hotels": ("7011", "Hotels"),
    "marriott": ("7011", "Hotels"),
    "hilton": ("7011", "Hotels"),
    "hyatt": ("7011", "Hotels"),
    "airbnb": ("7011", "Hotels"),
    "united": ("4511", "Air travel"),
    "delta": ("4511", "Air travel"),
    "aa": ("4511", "Air travel"),
    "southwest": ("4511", "Air travel"),
    "jetblue": ("4511", "Air travel"),
    "kayak": ("4722", "Travel"),
    "hertz": ("7512", "Car rental"),
    "enterprise": ("7512", "Car rental"),
    "avis": ("7512", "Car rental"),

    # transit and fuel
    "uber": ("4121", "Transit"),
    "lyft": ("4121", "Transit"),
    "shell": ("5541", "Fuel"),
    "chevron": ("5541", "Fuel"),
    "exxon": ("5541", "Fuel"),

    # streaming and digital
    "netflix": ("5815", "Streaming"),
    "spotify": ("5815", "Streaming"),
    "hulu": ("5815", "Streaming"),
    "disneyplus": ("5815", "Streaming"),
    "max": ("5815", "Streaming"),
    "youtube": ("5815", "Streaming"),
    "steampowered": ("5816", "Streaming"),
    "epicgames": ("5816", "Streaming"),

    # electronics, home, apparel, health
    "bestbuy": ("5732", "Electronics"),
    "apple": ("5732", "Electronics"),
    "newegg": ("5732", "Electronics"),
    "homedepot": ("5251", "Home improvement"),
    "lowes": ("5251", "Home improvement"),
    "ikea": ("5712", "Home improvement"),
    "wayfair": ("5712", "Home improvement"),
    "nordstrom": ("5651", "Fashion"),
    "zara": ("5651", "Fashion"),
    "uniqlo": ("5651", "Fashion"),
    "nike": ("5941", "Online retail"),
    "lululemon": ("5651", "Fashion"),
    "sephora": ("5977", "Beauty"),
    "ulta": ("5977", "Beauty"),
    "cvs": ("5912", "Drugstores"),
    "walgreens": ("5912", "Drugstores"),
}

# Words in a site's own name that point at a category when the domain does not.
# Weaker evidence than the table, and reported as such.
NAME_HINTS: list[tuple[str, str, str]] = [
    ("restaurant", "5812", "Dining"), ("cafe", "5814", "Dining"),
    ("pizza", "5814", "Dining"), ("kitchen", "5812", "Dining"),
    ("grocer", "5411", "Groceries"), ("market", "5411", "Groceries"),
    ("pharmacy", "5912", "Drugstores"), ("hotel", "7011", "Hotels"),
    ("airline", "4511", "Air travel"), ("airways", "4511", "Air travel"),
    ("travel", "4722", "Travel"), ("rental", "7512", "Car rental"),
    ("fashion", "5651", "Fashion"), ("apparel", "5651", "Fashion"),
    ("clothing", "5651", "Fashion"), ("beauty", "5977", "Beauty"),
    ("electronics", "5732", "Electronics"), ("hardware", "5251", "Home improvement"),
]

_HOST = re.compile(r"^(?:https?://)?(?:www\.)?([^/:]+)", re.I)
# Suffixes to strip before matching, so amazon.co.uk keys on "amazon".
_TLD = re.compile(r"\.(com|net|org|co|io|shop|store|us|uk|ca|au|sg|de|fr|jp)(\.[a-z]{2})?$", re.I)


def hostname(value: str | None) -> str:
    """The bare host, from a URL or a host that was already bare."""
    match = _HOST.match(str(value or "").strip())
    return (match.group(1) if match else "").lower()


def domain_key(host: str) -> str:
    """The registrable name, without www or a public suffix."""
    return _TLD.sub("", hostname(host)).rsplit(".", 1)[-1]


def resolve(url_or_host: str | None, merchant_name: str | None = None) -> dict:
    """Work out what this merchant is, and say how sure we are.

    Three tiers, reported honestly. A known domain is a fact. A category word in
    the site's own name is a hint. Anything else is unknown, and the caller
    should decline to recommend rather than guess a card.
    """
    host = hostname(url_or_host)
    key = domain_key(host)

    if key in DOMAIN_MCC:
        mcc, category = DOMAIN_MCC[key]
        return {"mcc": mcc, "category": category, "confidence": "high",
                "matchedOn": key, "host": host,
                "source": "Known merchant domain."}

    text = f"{merchant_name or ''} {host}".lower()
    for needle, mcc, category in NAME_HINTS:
        if needle in text:
            return {"mcc": mcc, "category": category, "confidence": "low",
                    "matchedOn": needle, "host": host,
                    "source": f"Guessed from the word '{needle}' in the site's name."}

    return {"mcc": None, "category": None, "confidence": "none",
            "matchedOn": None, "host": host,
            "source": "This merchant is not in the table and the name gives no category."}


def covers(mcc: str | None, category: str | None) -> list[str]:
    """Every code a rule for this category might legitimately list."""
    if not category:
        return [mcc] if mcc else []
    codes = CATEGORY_MCC.get(category.lower(), [])
    return list(dict.fromkeys([*( [mcc] if mcc else [] ), *codes]))
