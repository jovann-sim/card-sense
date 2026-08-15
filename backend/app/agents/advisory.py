from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .strategy import rule_matches, unmet_rule_conditions


log = logging.getLogger(__name__)


class AdvisoryWording(BaseModel):
    """Language Gemini may rewrite; financial facts are deliberately absent."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1, max_length=120)
    headline: str = Field(min_length=1, max_length=180)
    body: str = Field(min_length=1, max_length=500)


class AdvisoryWordingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendations: list[AdvisoryWording] = Field(default_factory=list, max_length=3)


class AdvisoryAgent:
    """Turn deterministic findings into advice without surrendering the facts."""

    id = "advisory"
    minimum_impact = 1.0

    def __init__(self, runtime):
        self.runtime = runtime

    def setup_actions(self, strategy, wallet):
        """Deterministic actions for eligibility and unreadable-card problems."""
        actions = []
        for category in strategy.get("categories", []):
            if "conditional-rate" not in (category.get("flags") or []):
                continue
            card = self._conditional_card_ref(wallet, category)
            actions.append({
                "id": f"rec-setup-{self._slug(category['category'])}",
                "urgency": "this-week",
                "headline": f"Verify the bonus eligibility for {category['category']}",
                "card": card,
                # Strategy excluded the conditional rate, so it cannot state a
                # monetary impact until eligibility is known.
                "impact": 0.0,
                "impactWindow": "unknown until verified",
                "body": (
                    f"{category.get('note') or 'The terms attach an unverified condition to this rate.'} "
                    "Confirm the condition before treating the bonus as available."
                ),
                "trace": [
                    {
                        "agent": "card-intelligence",
                        "detail": "The terms contain an eligibility condition that transactions alone cannot prove.",
                    },
                    {
                        "agent": "strategy",
                        "detail": f"Excluded the conditional {category['category']} rate from the reward calculation.",
                    },
                ],
            })

        for card in wallet:
            if card.get("parseStatus") == "parsed":
                continue
            actions.append({
                "id": f"rec-terms-{card.get('cardId') or self._slug(card.get('name', 'card'))}",
                "urgency": "this-week",
                "headline": f"Verify {card['name']}'s reward terms",
                "card": self._card_ref(wallet, card.get("name")),
                "impact": 0.0,
                "impactWindow": "unknown until read",
                "body": (
                    f"{card.get('parseNote') or 'The terms could not be read.'} "
                    "Enter the rates yourself, or provide a document the agent can read."
                ),
                "trace": [{
                    "agent": "card-intelligence",
                    "detail": f"Status {card.get('parseStatus')} — reason {card.get('failureReason') or 'unknown'}.",
                }],
            })
        return actions

    def run(self, strategy, forecast, wallet):
        candidates = self._candidates(strategy, wallet)
        if not candidates:
            return [*self.setup_actions(strategy, wallet), *self.routing_actions(strategy, wallet)]

        wording = self._generate_wording(candidates, forecast)
        by_category = {
            item.category.casefold(): item
            for item in wording.recommendations
        }
        recommendations = []
        for candidate in candidates:
            rewrite = by_category.get(candidate["category"].casefold())
            if rewrite and self._safe_wording(rewrite, candidate, wallet):
                candidate = {
                    **candidate,
                    "headline": rewrite.headline.strip(),
                    "body": rewrite.body.strip(),
                }
            recommendations.append({key: value for key, value in candidate.items() if key != "category"})

        # Setup actions name extracted conditions and must never be rewritten by
        # a model. Financial recommendations retain deterministic identities,
        # cards, impacts, windows and traces; Gemini controls wording only.
        return [*self.setup_actions(strategy, wallet), *recommendations,
                *self.routing_actions(strategy, wallet)]

    def routing_actions(self, strategy, wallet):
        """Advice about spending no card can reach directly.

        Rent, tuition and most insurance cannot go on a card at all, so pricing
        them at a card's rate produced advice that cannot be followed, about a
        reward that does not exist. The only mechanism that applies is a
        bill-payment service, and its fee is usually larger than the reward.

        Deterministic like the other setup actions, and for the same reason:
        the whole value here is arithmetic the user can check.
        """
        actions = []
        for row in strategy.get("routable", []):
            if row["spend"] <= 0:
                continue
            worth = row["worthIt"]
            cheapest = (row.get("alternatives") or [{}])[0]
            actions.append({
                "id": f"rec-bill-{self._slug(row['category'])}",
                "urgency": "informational",
                "headline": (
                    f"Route {row['category'].lower()} through {row['serviceName']}"
                    if worth else
                    f"{row['category']} cannot earn rewards — routing it costs more than it pays"
                ),
                "card": self._card_ref(wallet, row.get("bestCard")),
                "impact": abs(row["net"]),
                "impactWindow": "over the period, net of fees",
                "body": (
                    f"{row['verdict']} "
                    f"${row['spend']:,.2f} of {row['category'].lower()} would cost "
                    f"${row['fee']:,.2f} in fees and return ${row['reward']:,.2f} at "
                    f"{row['rewardRate'] * 100:.2f}%."
                    + (
                        f" The cheapest option modelled is {cheapest.get('name')} at "
                        f"{cheapest.get('feeRate', 0) * 100:.1f}%."
                        if cheapest.get("name") and cheapest.get("service") != row["service"] else ""
                    )
                    + ("" if worth else
                       " Reaching a welcome-bonus minimum is the one case where paying the fee wins.")
                ),
                "trace": [
                    {"agent": "ingestion",
                     "detail": f"{row['transactions']} transactions in {row['category']}, "
                               "flagged as payable only through a service."},
                    {"agent": "strategy",
                     "detail": f"Held out of the reward comparison because no card accepts it directly; "
                               f"priced against {row['serviceName']} at ${row['fee']:,.2f} fee "
                               f"versus ${row['reward']:,.2f} reward."},
                ],
            })
        return actions

    def _candidates(self, strategy, wallet):
        candidates = []
        for category in strategy.get("categories", []):
            try:
                impact = round(float(category.get("unclaimed") or 0), 2)
            except (TypeError, ValueError):
                continue
            if impact < self.minimum_impact:
                continue
            card = self._card_ref(wallet, category.get("bestCard"))
            if card is None:
                continue
            name = category.get("category") or "this spending"
            candidates.append({
                "category": name,
                "id": f"rec-route-{self._slug(name)}-{self._slug(card['name'])}",
                "urgency": "act-now" if not candidates else "this-week",
                "headline": f"Use {card['name']} for {name}",
                "card": card,
                "impact": impact,
                "impactWindow": "per period",
                "body": (
                    f"The verified strategy calculation found ${impact:.2f} of unclaimed reward value "
                    f"in {name}. Route eligible purchases to {card['name']} while its applicable cap allows."
                ),
                "trace": [{
                    "agent": "strategy",
                    "detail": f"Verified optimal value exceeds captured value by ${impact:.2f} in {name}.",
                }],
            })
            if len(candidates) == 3:
                break
        return candidates

    def _generate_wording(self, candidates, forecast):
        payload = {
            "recommendations": [
                {
                    "category": item["category"],
                    "cardName": item["card"]["name"],
                    "finding": "Verified strategy found meaningful unclaimed reward value in this category.",
                }
                for item in candidates
            ],
            "forecastContext": {
                "window": forecast.get("doNothingWindow"),
                "quality": forecast.get("quality"),
            },
        }
        prompt = (
            "Rewrite each supplied recommendation as a concise imperative headline and a two-sentence body. "
            "Return exactly the supplied category string so the wording can be joined back to verified facts. "
            "Use the supplied card name exactly. Do not add, calculate, or mention any number, amount, rate, "
            "deadline, reward value, card, or category that is not supplied. Financial fields are deliberately "
            "not part of your output; the application attaches them after validation.\n\n"
            f"INPUT:\n{json.dumps(payload, default=str)}"
        )
        try:
            return self.runtime.structured(prompt, AdvisoryWordingOutput)
        except Exception as exc:
            log.warning("Advisory wording unavailable; using deterministic copy: %s", exc)
            return AdvisoryWordingOutput()

    def _safe_wording(self, wording, candidate, wallet):
        text = f"{wording.headline} {wording.body}"
        folded = text.casefold()
        if candidate["card"]["name"].casefold() not in folded:
            return False
        if candidate["category"].casefold() not in folded:
            return False
        # Gemini is not allowed to introduce financial claims. Dollar figures,
        # percentages and quantified rewards always come from Strategy instead.
        if re.search(r"(?:[$€£]\s*\d|\d+(?:\.\d+)?\s*(?:%|points?|miles?|dollars?))", text, re.I):
            return False
        for card in wallet:
            other = str(card.get("name") or "")
            if other and other != candidate["card"]["name"] and other.casefold() in folded:
                return False
        return True

    def _card_ref(self, wallet, name):
        card = next((item for item in wallet if item.get("name") == name), None)
        if not card:
            return None
        last4 = str(card.get("last4") or "")
        return {"name": card["name"], "last4": last4} if last4 else None

    def _conditional_card_ref(self, wallet, category):
        for card in wallet:
            for rule in card.get("rules") or []:
                if rule_matches(rule, category.get("category")) and unmet_rule_conditions(rule):
                    return self._card_ref(wallet, card.get("name"))
        return self._card_ref(wallet, category.get("bestCard"))

    def _slug(self, value):
        return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "item"
