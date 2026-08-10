from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone

from ..config import settings
from .runtime import ModelUnavailable
from ..valuations import BASE_CURRENCY, DIVERGENCE_TOLERANCE, divergence, unit_value
from .schema import (
    EXTRACTION_PROMPT,
    ExtractionResult,
    choose_reward,
    display_rate,
    option_value,
    spend_cap,
    value_per_dollar,
)
from .terms import FetchError, TermsDocument, document_from_text, fetch_terms

log = logging.getLogger(__name__)

# Failures the card can recover from by itself on the next scheduled pass; the
# rules we already hold stay usable in the meantime, so the card goes stale
# rather than failed.
TRANSIENT = {"rate_limited", "model_unavailable", "fetch_failed"}

NOTES = {
    "fetch_failed": "The terms document could not be retrieved, so the rates on file were left unchanged.",
    "rate_limited": "The source refused repeated requests. The rates on file may be out of date.",
    "unsupported_content": "That link does not lead to a readable terms document.",
    "model_unavailable": "The document could not be read right now. The rates on file were left unchanged.",
    "no_rules_found": "The document was read but states no reward rates, so this card is excluded from comparisons.",
    "low_confidence": "The rates could not be read confidently, so this card is excluded rather than guessed at.",
    "no_source": "No terms link or text was supplied, so there is nothing to read.",
}


CHANNEL_WORDS = {
    "online": "online only",
    "in_store": "in store only",
    "contactless": "contactless only",
    "foreign_currency": "foreign currency only",
}

CONDITION_WORDS = {
    "minimum_spend": "minimum spend",
    "enrolment": "enrolment required",
    "category_selection": "you choose the category",
    "banking_relationship": "requires a linked account",
    "new_customer": "new customers only",
    "promotional_period": "time-limited",
    "spend_elsewhere": "requires spend elsewhere",
}


def with_rule_ids(rules: list[dict]) -> list[dict]:
    """Attach deterministic, sibling-unique IDs to projected reward rules."""
    used: set[str] = set()
    identified: list[dict] = []
    for rule in rules:
        data = {**rule}
        payload = {key: value for key, value in data.items() if key != "id"}
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()[:16]
        base = str(data.get("id") or f"rule-{digest}")
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}-{suffix}"
            suffix += 1
        data["id"] = candidate
        used.add(candidate)
        identified.append(data)
    return identified


def _restrictions(rule: dict) -> list[str]:
    """Short phrases naming everything that narrows a rate.

    Collected here so the interface can show why a headline number will not
    apply to most of a user's spending — the difference between "4% on dining"
    and "4% at three named restaurants, if you enrol".
    """
    out: list[str] = []
    if rule.get("merchants"):
        named = ", ".join(rule["merchants"][:4])
        more = len(rule["merchants"]) - 4
        out.append(f"only at {named}{f' and {more} more' if more > 0 else ''}")
    for channel in rule.get("channels") or []:
        if channel in CHANNEL_WORDS:
            out.append(CHANNEL_WORDS[channel])
    if rule.get("requiresSelection"):
        out.append("you must nominate this category")
    if rule.get("minSpend"):
        out.append(f"minimum spend {rule['minSpend']:,.0f}")
    for condition in rule.get("conditions") or []:
        label = CONDITION_WORDS.get(condition.get("kind", ""), None)
        if label and label not in out:
            out.append(label)
    if rule.get("exclusions"):
        out.append(f"{len(rule['exclusions'])} exclusion{'s' if len(rule['exclusions']) > 1 else ''}")
    return out


class CardIntelligenceAgent:
    """Turns a published terms document into reward rules the optimiser can price.

    Deliberately conservative: it will exclude a card rather than assert a rate
    it is not sure about, because a wrong rate produces confident bad advice,
    which is worse than no advice.
    """

    id = "card-intelligence"

    def __init__(self, runtime):
        self.runtime = runtime

    def parse(self, card: dict, previous: dict | None = None) -> dict:
        """Read a card's terms. `previous` lets a transient failure degrade to stale."""
        document, failure = self._resolve_document(card)
        if failure:
            return self._failure(failure, previous, locator=card.get("termsUrl") or "not supplied")
        return self.parse_document(document, card, previous)

    def parse_document(self, document: TermsDocument, card: dict, previous: dict | None = None) -> dict:
        """Extract from a document already in hand — a fetch, a paste, or an upload."""
        try:
            extraction = self.runtime.structured(EXTRACTION_PROMPT, ExtractionResult, document=document)
        except ModelUnavailable as exc:
            log.warning("Card intelligence model failure (%s): %s", exc.reason, exc.detail)
            return self._failure(exc.reason, previous, locator=document.locator)

        if not extraction.rules:
            return self._failure("no_rules_found", previous, locator=document.locator, terminal=True)
        if extraction.confidence < settings.extraction_min_confidence:
            return self._failure("low_confidence", previous, locator=document.locator, terminal=True)

        return self._success(extraction, document, card)

    # ---------------------------------------------------------------- input --

    def _resolve_document(self, card: dict) -> tuple[TermsDocument | None, str | None]:
        if card.get("termsText"):
            return document_from_text(card["termsText"]), None
        url = (card.get("termsUrl") or "").strip()
        if not url:
            return None, "no_source"
        if not url.lower().startswith(("http://", "https://")):
            return None, "unsupported_content"
        try:
            return fetch_terms(url), None
        except FetchError as exc:
            log.warning("Card intelligence fetch failure (%s): %s", exc.reason, exc.detail)
            return None, exc.reason

    # --------------------------------------------------------------- output --

    def _success(self, extraction: ExtractionResult, document: TermsDocument, card: dict) -> dict:
        characteristics = extraction.characteristics.model_dump(exclude_none=True)
        programme = characteristics.get("rewardCurrency")
        # A card's own terms decide its currency. We label rather than convert:
        # applying an FX rate we invented would be worse than saying "this is USD".
        currency = (characteristics.get("currency") or BASE_CURRENCY).upper()

        track = card.get("track")
        warnings: list[str] = []
        rules = []
        for rule in extraction.rules:
            data = rule.model_dump()

            # A card may pay in more than one currency. Which one is real
            # depends on what this holder said they are collecting.
            chosen = choose_reward(data.get("rewards"), track)
            if chosen:
                data["rewardType"] = chosen["rewardType"]
                data["rateValue"] = chosen["rateValue"]
                data["rateUnit"] = chosen["rateUnit"]
                data["rewardCurrency"] = chosen.get("rewardCurrency") or programme
            rule_programme = data.get("rewardCurrency") or programme

            priced = spend_cap(data)
            unit_priced, unit_source = unit_value(rule_programme, data.get("rewardType", "cashback"))
            alternatives = [
                {**option, "valuePerDollar": option_value(option)}
                for option in (data.get("rewards") or [])
                if chosen is None or option != chosen
            ]

            # Same reward, two currencies: if they do not price alike, one of
            # the valuations or the conversion has been misread.
            option_values = [option_value(o) for o in (data.get("rewards") or [])]
            spread = divergence(option_values)
            if spread > DIVERGENCE_TOLERANCE:
                warnings.append(
                    f"{data['categoryLabel']}: the reward options price {spread:.0%} apart "
                    f"({', '.join(f'{v:.3f}' for v in sorted(option_values))} per dollar). "
                    "One of the conversions or programme valuations is likely wrong."
                )
            rules.append({
                **data,
                "alternativeRewards": alternatives,
                "hasRewardChoice": len(data.get("rewards") or []) > 1,
                # Everything a rate depends on, in one place the UI can read.
                "restrictions": _restrictions(data),
                # `cap` means spend in the card's billing currency, always —
                # a reward cap ("9,000 points a month") is divided back through
                # the earn rate first. Everything downstream, interface included,
                # can then treat it as dollars without asking what kind it is.
                "cap": priced,
                "capSpend": priced,
                # The document's own figure, kept so provenance stays honest.
                "capValue": data.get("cap"),
                # Kept so existing consumers that render a string still work.
                "rate": display_rate(data),
                # The field every calculation should actually use, priced
                # through this card's own programme rather than a flat rate.
                "valuePerDollar": value_per_dollar(data, rule_programme),
                "rewardCurrency": rule_programme,
                "rewardUnitValue": unit_priced,
                "rewardUnitValueSource": unit_source,
                "currency": currency,
            })
        rules.sort(key=lambda item: item["valuePerDollar"], reverse=True)
        rules = with_rule_ids(rules)

        today = datetime.now(timezone.utc).date()
        return {
            "rules": rules,
            "characteristics": characteristics,
            "status": "parsed",
            "confidence": round(extraction.confidence, 2),
            "note": None,
            "failureReason": None,
            "source": {
                "label": self._source_label(document),
                "locator": document.locator,
                "retrievedAt": today.isoformat(),
            },
            "recheckCadence": "weekly",
            "nextRecheckAt": str(today + timedelta(days=7)),
            "documentSummary": extraction.documentSummary,
            "currency": currency,
            # Structures the model saw but could not express, plus anything
            # that did not add up. Surfaced rather than dropped, because a
            # known gap beats a silent wrong number.
            "unresolved": [*extraction.unresolved, *warnings],
            # Prefer what the document says over what the form claimed.
            "annualFee": characteristics.get("annualFee", card.get("annualFee")),
        }

    def _failure(self, reason: str, previous: dict | None, *, locator: str, terminal: bool = False) -> dict:
        note = NOTES.get(reason, "The terms could not be read.")
        keep = previous.get("rules") if previous else None
        today = datetime.now(timezone.utc).date()

        # Holding rules we already read beats dropping a working card because a
        # single recheck failed.
        if keep and not terminal and reason in TRANSIENT:
            source = dict(previous.get("source") or {})
            return {
                "rules": keep,
                "characteristics": previous.get("characteristics", {}),
                "status": "stale",
                "confidence": previous.get("confidence", 0.0),
                "note": note,
                "failureReason": reason,
                "source": source or {"label": "Previously read terms", "locator": locator, "retrievedAt": str(today)},
                "recheckCadence": "daily",
                "nextRecheckAt": str(today + timedelta(days=1)),
            }

        return {
            "rules": [],
            "characteristics": {},
            "status": "failed",
            "confidence": 0.0,
            "note": note,
            "failureReason": reason,
            "source": {"label": "Could not be read", "locator": locator, "retrievedAt": str(today)},
            "recheckCadence": "weekly" if reason not in TRANSIENT else "daily",
            "nextRecheckAt": str(today + timedelta(days=1 if reason in TRANSIENT else 7)),
        }

    def _source_label(self, document: TermsDocument) -> str:
        if document.is_pdf:
            return "Issuer terms PDF"
        if document.locator == "pasted text":
            return "Terms text you supplied"
        return "Issuer terms page"

    # ---------------------------------------------------------------- recheck --

    def due_for_recheck(self, card: dict, today: date | None = None) -> bool:
        due = card.get("nextRecheckAt")
        if not due:
            return True
        return str(due) <= str(today or datetime.now(timezone.utc).date())
