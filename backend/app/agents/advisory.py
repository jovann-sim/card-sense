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

    def run(self, strategy, forecast, wallet, welcome=None, simulation=None):
        planned = self.plan_actions(simulation, wallet)
        candidates = [] if planned else self._candidates(strategy, wallet)
        if not candidates:
            return [*self.welcome_actions(welcome or [], wallet), *planned,
                    *self.setup_actions(strategy, wallet), *self.routing_actions(strategy, wallet)]

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
        # A bonus deadline outranks an optimisation: it expires, and the rest
        # can be taken tomorrow at no cost.
        return [*self.welcome_actions(welcome or [], wallet), *planned, *self.setup_actions(strategy, wallet),
                *recommendations, *self.routing_actions(strategy, wallet)]

    def verdict(self, merchant, wallet, rules, strategy=None, transactions=None):
        """Which card to reach for at one merchant, right now.

        The point query behind the browser extension. It answers from the same
        rules and the same optimiser as the dashboard, so the extension cannot
        drift from the site — and it declines rather than guesses, because a
        confident wrong card at checkout is worse than no popup at all.

        It never sees a page's contents, a form field or a card number. A
        hostname and a site name are the whole input.
        """
        from ..agents.strategy import rule_matches, rule_rate

        if not merchant.get("mcc"):
            return {
                "merchant": merchant.get("host") or "this page",
                "known": False,
                "card": None,
                "reason": merchant["source"],
                "trace": [{"agent": "ingestion", "detail": merchant["source"]}],
            }

        ranked = []
        for card in wallet:
            if card.get("parseStatus") != "parsed":
                continue
            best = None
            for rule in rules.get(card.get("cardId"), []):
                if not rule_matches(rule, merchant["category"], merchant["mcc"]):
                    continue
                rate = rule_rate(rule, card.get("track"))
                if best is None or rate > best[0]:
                    best = (rate, rule)
            if best:
                ranked.append((best[0], card, best[1]))
        ranked.sort(key=lambda row: row[0], reverse=True)

        if not ranked:
            return {
                "merchant": merchant.get("host"),
                "known": True,
                "category": merchant["category"],
                "mcc": merchant["mcc"],
                "card": None,
                "reason": "None of your cards has a readable rule covering this category.",
                "trace": [{"agent": "card-intelligence",
                           "detail": "No parsed rule matched this merchant category code."}],
            }

        rate, card, rule = ranked[0]
        runner = ranked[1] if len(ranked) > 1 else None
        # A tie is a tie. Presenting one of two identical cards as the answer
        # implies a difference the arithmetic does not support.
        tied = runner and abs(runner[0] - rate) < 0.0001

        from ..agents.forecast import ForecastAgent

        cap = ForecastAgent().cap_headroom(card, rule, transactions or [])
        caveat = cap.get("reason")
        conditions = unmet_rule_conditions(rule)
        if conditions:
            caveat = conditions[0]

        terms_confidence = float(card.get("parseConfidence", card.get("confidence", 1.0)))
        recommendation_confidence = (
            "low" if merchant["confidence"] == "low" or terms_confidence < 0.5
            else "high" if merchant["confidence"] == "high" and terms_confidence >= 0.8
            else "medium"
        )

        return {
            "merchant": merchant.get("host"),
            "known": True,
            "category": merchant["category"],
            "mcc": merchant["mcc"],
            "confidence": merchant["confidence"],
            "recommendationConfidence": recommendation_confidence,
            "card": {
                "name": card["name"], "last4": card.get("last4", "0000"),
                "termsConfidence": round(terms_confidence, 2),
            },
            "rate": rule.get("rate", "—"),
            "valuePerDollar": round(rate, 4),
            "cap": cap,
            "reason": (
                f"Pays about ${rate:,.3f} per dollar here"
                + (
                    f", ${rate - runner[0]:,.3f} more than {runner[1]['name']}."
                    if runner and not tied else
                    f" — the same as {runner[1]['name']}, so either is fine." if tied else "."
                )
            ),
            "caveat": caveat,
            "runnerUp": (
                f"{runner[1]['name']} ••{runner[1].get('last4', '0000')} · {runner[2].get('rate', '—')}"
                if runner else None
            ),
            "tied": bool(tied),
            "trace": [
                {"agent": "ingestion",
                 "detail": f"Merchant resolved to MCC {merchant['mcc']} ({merchant['category']}). {merchant['source']}"},
                {"agent": "card-intelligence",
                 "detail": f"{card['name']} terms: {rule.get('rate', '—')} on {rule.get('categoryLabel', 'this category')}."},
                {"agent": "strategy",
                 "detail": f"Ranked {len(ranked)} of {len(wallet)} cards by value per dollar for this code."},
            ],
        }

    def plan_actions(self, simulation, wallet):
        """The simulator's ranked answer, as advice rather than a table.

        These are deterministic: every figure comes from re-pricing the whole
        history against a different set of cards. The model never sees them, so
        it cannot round a number or invent a card.
        """
        actions = []
        for step in (simulation or {}).get("steps", []):
            if step["value"] <= 0:
                continue
            card = self._card_ref(wallet, step.get("card"))
            actions.append({
                "id": f"rec-plan-{step['rank']}-{self._slug(step['kind'])}",
                "urgency": "act-now" if step["rank"] == 1 else "this-week",
                "headline": step["title"],
                # A reassignment points at a card the user actually holds, so
                # resolve its real identifier from the wallet. Acquisition and
                # routing steps do not identify a held card and should carry no
                # card reference rather than displaying a fabricated ••0000.
                "card": card,
                "impact": round(float(step["value"]), 2),
                "impactWindow": step["valueWindow"],
                "body": step["detail"],
                "trace": [{
                    "agent": "strategy",
                    "detail": (
                        "Re-priced the full transaction history against this arrangement "
                        "of cards, respecting every cap and eligibility condition."
                    ),
                }],
            })
        return actions

    def welcome_actions(self, welcome, wallet):
        """A deadline that costs real money if it passes.

        Everything else in this product is an optimisation the user can take or
        leave. A welcome bonus is worth more than a year of ordinary earn and it
        expires, so missing one by two hundred dollars of spending loses several
        hundred. It gets the only genuine urgency in the list.
        """
        actions = []
        for row in welcome:
            if row["state"] in {"met", "missed"}:
                continue
            rescue = row.get("rescue")
            urgency = "act-now" if row["state"] == "at-risk" else "this-week"
            body = (
                f"${row['qualifyingSpend']:,.2f} of the ${row['minSpend']:,.0f} minimum is done, "
                f"leaving ${row['gap']:,.2f} in {row['daysLeft']} days. "
                f"That needs ${row['perDayNeeded']:,.2f} a day against the "
                f"${row['perDayCurrent']:,.2f} you are averaging."
            )
            if rescue and rescue["worthIt"]:
                # The one case where paying a bill service its fee is a good
                # trade rather than a losing one.
                body += (
                    f" Routing ${rescue['spendToRoute']:,.2f} of bills through "
                    f"{rescue['serviceName']} would close it for ${rescue['fee']:,.2f} in fees "
                    f"and still net ${rescue['net']:,.2f}."
                )
            actions.append({
                "id": f"rec-welcome-{self._slug(row['card'])}",
                "urgency": urgency,
                "headline": (
                    f"{row['card']}: ${row['gap']:,.0f} short of a ${row['valueUsd']:,.0f} bonus"
                    if row["state"] == "at-risk" else
                    f"{row['card']} is on track for its ${row['valueUsd']:,.0f} bonus"
                ),
                # Bonus progress is only actionable for a card in the wallet.
                # Resolve the actual identifier and decline to fabricate one
                # when legacy or inconsistent progress data names no held card.
                "card": self._card_ref(wallet, row["card"]),
                "impact": row["valueUsd"],
                "impactWindow": f"one-time, by {row['deadline']}",
                "deadline": row["deadline"],
                "body": body,
                "trace": [
                    {"agent": "card-intelligence",
                     "detail": f"Terms state {row['award']:,.0f} {row['unit']} after "
                               f"${row['minSpend']:,.0f} of spend within {row['daysLeft'] + 0} days of opening."},
                    {"agent": "ingestion",
                     "detail": f"{row['transactions']} qualifying purchases on this card since "
                               f"{row['openedAt']} total ${row['qualifyingSpend']:,.2f}."},
                ],
            })
        return actions

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
