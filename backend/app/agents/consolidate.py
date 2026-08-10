from __future__ import annotations

import re

from .schema import ExtractionResult

# Reading the same document twice does not produce the same answer. Across
# three eval runs of ten hard cards the capture rate moved between 70% and 80%,
# and — crucially — the misses moved too: a run that dropped a nomination
# requirement caught a spend-elsewhere condition, and the next run did the
# reverse. Uncorrelated misses are exactly the case where a second pass pays.
#
# So extraction runs twice and the passes are merged additively: a condition
# either pass found is kept, because these documents state their qualifiers
# once and missing one silently overstates the card. Nothing is invented by
# merging — every field still came from the document via one of the passes.


def _key(label: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (label or "").lower()).strip()


def _union(primary: list, secondary: list) -> list:
    """Order-preserving union of two lists of scalars."""
    out = list(primary or [])
    for item in secondary or []:
        if item not in out:
            out.append(item)
    return out


def _merge_conditions(primary: list[dict], secondary: list[dict]) -> list[dict]:
    """One entry per condition kind, keeping whichever pass said more."""
    merged = {c.get("kind"): dict(c) for c in primary or []}
    for condition in secondary or []:
        kind = condition.get("kind")
        existing = merged.get(kind)
        if not existing:
            merged[kind] = dict(condition)
            continue
        for field in ("amount", "count"):
            if existing.get(field) is None and condition.get(field) is not None:
                existing[field] = condition[field]
        if len(condition.get("description") or "") > len(existing.get("description") or ""):
            existing["description"] = condition["description"]
    return list(merged.values())


def _merge_rule(primary: dict, secondary: dict) -> dict:
    merged = dict(primary)
    for field in ("mccCodes", "merchants", "channels", "exclusions", "selectableCategories"):
        merged[field] = _union(primary.get(field), secondary.get(field))
    merged["conditions"] = _merge_conditions(primary.get("conditions"), secondary.get("conditions"))
    merged["requiresSelection"] = bool(primary.get("requiresSelection") or secondary.get("requiresSelection"))
    merged["stacksWithBase"] = bool(primary.get("stacksWithBase") or secondary.get("stacksWithBase"))

    # A stated cap beats an absent one; the same for the qualifiers.
    for field in ("cap", "capType", "minSpend", "capGroup", "notes"):
        if merged.get(field) is None and secondary.get(field) is not None:
            merged[field] = secondary[field]

    # Keep every reward currency either pass identified.
    seen = {(r.get("rewardType"), r.get("rateUnit"), r.get("rateValue")) for r in merged.get("rewards") or []}
    for reward in secondary.get("rewards") or []:
        if (reward.get("rewardType"), reward.get("rateUnit"), reward.get("rateValue")) not in seen:
            merged.setdefault("rewards", []).append(reward)
    return merged


def consolidate(passes: list[ExtractionResult]) -> ExtractionResult:
    """Merge repeated readings of one document into the most complete view.

    The pass that found the most rules is the base, since rule count is the
    best available proxy for how thoroughly a pass read the document.
    """
    # A card can be entirely benefits — a fixed quarterly rebate earns no
    # percentage — so a pass with benefits and no rules is still a real reading.
    usable = [p for p in passes if p and (p.rules or p.benefits)]
    if not usable:
        return passes[0] if passes else ExtractionResult()
    if len(usable) == 1:
        return usable[0]

    ordered = sorted(usable, key=lambda p: (len(p.rules), len(p.benefits), p.confidence), reverse=True)
    base = ordered[0].model_dump()

    for other in ordered[1:]:
        extra = other.model_dump()
        by_key = {_key(r["categoryLabel"]): i for i, r in enumerate(base["rules"])}

        for rule in extra["rules"]:
            index = by_key.get(_key(rule["categoryLabel"]))
            if index is None:
                continue  # A rule only one pass saw is not corroborated; leave it.
            base["rules"][index] = _merge_rule(base["rules"][index], rule)

        for field, value in (extra.get("characteristics") or {}).items():
            if base["characteristics"].get(field) in (None, [], "") and value not in (None, [], ""):
                base["characteristics"][field] = value

        labels = {b.get("label") for b in base.get("benefits") or []}
        for benefit in extra.get("benefits") or []:
            if benefit.get("label") not in labels:
                base.setdefault("benefits", []).append(benefit)

        base["unresolved"] = _union(base.get("unresolved"), extra.get("unresolved"))
        base["confidence"] = max(base.get("confidence", 0), extra.get("confidence", 0))

    return ExtractionResult.model_validate(base)
