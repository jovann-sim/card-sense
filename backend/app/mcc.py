from __future__ import annotations

import re

# Merchant category codes by spending category.
#
# The model supplies these when a document names them, but it omits them
# inconsistently — the same terms returned 31 codes on one run and none on the
# next. Without codes, rule matching silently degrades to comparing category
# labels, where "Travel" and "Transport" read alike and mean different things.
# This table backfills the gap so matching never quietly gets worse.
#
# Ranges are inclusive and written "3000-3299".
CATEGORY_MCC: dict[str, list[str]] = {
    "dining": ["5811", "5812", "5813", "5814"],
    "groceries": ["5411", "5422", "5441", "5451", "5462", "5499"],
    "fuel": ["5541", "5542", "5983"],
    "transit": ["4111", "4112", "4121", "4131", "4789"],
    "air travel": ["3000-3299", "4511"],
    "hotels": ["3500-3999", "7011"],
    "travel": ["3000-3299", "3500-3999", "4111", "4511", "4722", "7011", "7512"],
    "car rental": ["3351-3500", "7512", "7513", "7519"],
    "online retail": ["5262", "5310", "5399", "5964", "5969"],
    "department stores": ["5311", "5300", "5399"],
    "fashion": ["5611", "5621", "5631", "5641", "5651", "5655", "5661", "5691", "5699"],
    "beauty": ["5977", "7230", "7297", "7298"],
    "wellness": ["7297", "7298", "8043", "8049"],
    "entertainment": ["7832", "7841", "7911", "7922", "7929", "7991", "7996", "7998", "7999"],
    "streaming": ["4899", "5815", "5816", "5817", "5818"],
    "drugstores": ["5122", "5912"],
    "utilities": ["4814", "4899", "4900"],
    "insurance": ["5960", "6300"],
    "education": ["8211", "8220", "8241", "8244", "8249", "8299"],
    "home improvement": ["5200", "5211", "5231", "5251", "5261", "5712"],
    "fitness": ["7997", "7941"],
    "electronics": ["5722", "5732", "5734"],
    "pharmacy": ["5122", "5912"],
    "taxi": ["4121"],
    "public transport": ["4111", "4131"],
    "supermarkets": ["5411", "5422", "5451"],
    "food delivery": ["5811", "5812", "5814"],
    "wholesale clubs": ["5300", "5310"],
    "government": ["9211", "9222", "9223", "9311", "9399"],
}

# Words in a category label that point at one of the keys above. Ordered most
# specific first, because "travel" appears inside "air travel".
ALIASES: list[tuple[str, str]] = [
    ("air travel", "air travel"), ("airline", "air travel"), ("flight", "air travel"),
    ("hotel", "hotels"), ("accommodation", "hotels"), ("car rental", "car rental"),
    ("public transport", "public transport"), ("rideshare", "taxi"), ("taxi", "taxi"),
    ("transport", "transit"), ("transit", "transit"), ("commut", "transit"),
    ("restaurant", "dining"), ("dining", "dining"), ("food delivery", "food delivery"),
    ("f&b", "dining"), ("eating", "dining"), ("cafe", "dining"),
    ("grocer", "groceries"), ("supermarket", "supermarkets"), ("wholesale", "wholesale clubs"),
    ("petrol", "fuel"), ("gas station", "fuel"), ("fuel", "fuel"),
    ("department store", "department stores"), ("online", "online retail"),
    ("e-commerce", "online retail"), ("shopping", "online retail"),
    ("apparel", "fashion"), ("fashion", "fashion"), ("clothing", "fashion"),
    ("bags and shoes", "fashion"), ("beauty", "beauty"), ("wellness", "wellness"),
    ("entertainment", "entertainment"), ("cinema", "entertainment"),
    ("streaming", "streaming"), ("subscription", "streaming"),
    ("drugstore", "drugstores"), ("pharmacy", "pharmacy"),
    ("utilit", "utilities"), ("insurance", "insurance"), ("education", "education"),
    ("home improvement", "home improvement"), ("furnishing", "home improvement"),
    ("fitness", "fitness"), ("gym", "fitness"), ("electronic", "electronics"),
    ("government", "government"), ("travel", "travel"),
]


def codes_for(label: str | None) -> list[str]:
    """Standard MCCs for a category label, or an empty list if we cannot tell.

    Returning nothing is the right answer for a label like "Everything else" or
    a nominated-category placeholder — inventing codes there would narrow a
    rule that is deliberately broad.
    """
    if not label:
        return []
    text = re.sub(r"[^a-z& ]+", " ", label.lower())

    if any(word in text for word in ("everything else", "all other", "base", "general", "other spend")):
        return []

    matched: list[str] = []
    for needle, key in ALIASES:
        if needle not in text:
            continue
        for code in CATEGORY_MCC[key]:
            if code not in matched:
                matched.append(code)
        # Consume the words this alias claimed, so a broader one cannot match
        # the same characters again. The list is ordered specific-first for
        # exactly this reason, but reading it without consuming meant "Air
        # travel" also matched "travel" and inherited hotels and car rental —
        # a rule that pays a bonus on flights would have paid it on a hotel.
        # A genuinely compound label like "Dining and travel" still gets both,
        # because the second alias matches words the first one left alone.
        text = text.replace(needle, " ")
    return matched


def backfill(rules: list[dict]) -> tuple[list[dict], int]:
    """Add standard codes to rules the model left without any.

    Only fills empty lists — codes the document actually named always win,
    because an issuer's own list is authoritative and ours is a convenience.
    """
    filled = 0
    for rule in rules:
        if rule.get("mccCodes"):
            continue
        # A rate limited to named merchants is not a category rate; giving it
        # category codes would let it match spending it does not cover.
        if rule.get("merchants"):
            continue
        codes = codes_for(rule.get("categoryLabel"))
        if codes:
            rule["mccCodes"] = codes
            rule["mccSource"] = "inferred"
            filled += 1
    return rules, filled
