from __future__ import annotations
from .runtime import GeminiRuntime

class AdvisoryAgent:
    id="advisory"
    def __init__(self,runtime): self.runtime=runtime
    def setup_actions(self, strategy, wallet):
        """Advice about the card, not the spending.

        A rate that needs a nominated category or a linked account is worth
        nothing until the holder does that. Reporting the gap as unclaimed
        without saying what unlocks it makes the number look like a mystery.
        """
        actions = []
        for category in strategy.get("categories", []):
            if "conditional-rate" not in (category.get("flags") or []):
                continue
            actions.append({
                "id": f"rec-setup-{category['category'].lower().replace(' ', '-')}",
                "urgency": "this-week",
                "headline": f"Unlock the bonus rate on {category['category']}",
                "card": {"name": category.get("bestCard", "your card"), "last4": "0000"},
                "impact": category.get("unclaimed", 0),
                "impactWindow": "per period",
                "body": (
                    f"{category.get('note') or 'This rate depends on something you have not set up.'} "
                    f"Until then the {category['category']} spending earns the base rate, "
                    f"and the gap stays at ${category.get('unclaimed', 0):.2f}."
                ),
                "trace": [
                    {"agent": "card-intelligence",
                     "detail": "The terms make this rate conditional; the condition was recorded rather than assumed met."},
                    {"agent": "strategy",
                     "detail": f"Priced {category['category']} at the base rate because the condition is unverified."},
                ],
            })

        # Cards excluded from every comparison because their terms never read.
        for card in wallet:
            if card.get("parseStatus") == "parsed":
                continue
            actions.append({
                "id": f"rec-terms-{card.get('cardId', card.get('last4', 'card'))}",
                "urgency": "this-week",
                "headline": f"{card['name']} is excluded until its rates are known",
                "card": {"name": card["name"], "last4": card.get("last4", "0000")},
                "impact": 0,
                "impactWindow": "unknown until read",
                "body": (
                    f"{card.get('parseNote') or 'The terms could not be read.'} "
                    "Enter the rates yourself, or point the agent at a document it can read."
                ),
                "trace": [{
                    "agent": "card-intelligence",
                    "detail": f"Status {card.get('parseStatus')} — "
                              f"reason {card.get('failureReason') or 'unknown'}.",
                }],
            })
        return actions

    def routing_actions(self, strategy):
        """Advice about spending no card can reach directly.

        Rent, tuition and most insurance cannot go on a card at all, so the
        agent used to price them at a card's rate and recommend "put rent on
        your Journey card" — advice that cannot be followed, about a reward
        that does not exist. The only mechanism that applies is a bill-payment
        service, and its fee is usually larger than the reward.

        These are written deterministically rather than by the model, because
        the whole value here is arithmetic the user can check.
        """
        actions = []
        for row in strategy.get("routable", []):
            if row["spend"] <= 0:
                continue
            worth = row["worthIt"]
            cheapest = (row.get("alternatives") or [{}])[0]
            actions.append({
                "id": f"rec-route-{row['category'].lower().replace(' ', '-')}",
                "urgency": "informational",
                "headline": (
                    f"Route {row['category'].lower()} through {row['serviceName']}"
                    if worth else
                    f"{row['category']} cannot earn rewards — and routing it costs more than it pays"
                ),
                "card": {"name": row.get("bestCard") or "your best card", "last4": "0000"},
                "impact": abs(row["net"]),
                "impactWindow": "over the period, net of fees",
                "body": (
                    f"{row['verdict']} "
                    f"{row['spend']:,.2f} of {row['category'].lower()} would cost "
                    f"{row['fee']:,.2f} in fees and return {row['reward']:,.2f} at "
                    f"{row['rewardRate'] * 100:.2f}%."
                    + (
                        f" The cheapest option modelled is {cheapest.get('name')} at "
                        f"{cheapest.get('feeRate', 0) * 100:.1f}%."
                        if cheapest.get("name") and cheapest.get("service") != row["service"] else ""
                    )
                    + (
                        ""
                        if worth else
                        " Reaching a welcome-bonus minimum is the one case where paying the fee wins."
                    )
                ),
                "trace": [
                    {"agent": "ingestion",
                     "detail": f"{row['transactions']} transactions in {row['category']}, "
                               f"flagged as payable only through a service."},
                    {"agent": "strategy",
                     "detail": f"Held out of the reward comparison because no card accepts it directly; "
                               f"priced against {row['serviceName']} at "
                               f"{row['fee']:,.2f} fee versus {row['reward']:,.2f} reward."},
                ],
            })
        return actions

    def run(self, strategy, forecast, wallet):
        top=strategy["categories"][:3]
        fallback=[{"id":f"rec-{i}","urgency":"act-now" if i==0 else "this-week","headline":f"Review {x['category']} — {x['bestCard']} is the best available option","card":{"name":x['bestCard'],"last4":"0000"},"impact":x["unclaimed"],"impactWindow":"per period","body":f"The deterministic strategy simulation found ${x['unclaimed']:.2f} of potential reward value in {x['category']}. Use {x['bestCard']} where the applicable rule and cap allow it.","trace":[{"agent":"strategy","detail":f"Optimal value exceeds captured value by ${x['unclaimed']:.2f}."}]} for i,x in enumerate(top)]
        result = self.runtime.json(
            "Turn deterministic financial findings into concise imperative recommendations. "
            "Never invent figures. Return a JSON array named recommendations. "
            "Only the categories given to you can go on a credit card. Never suggest paying "
            "rent, tuition, insurance or a utility bill with a card to earn rewards: those "
            "billers do not accept cards, and that spending has already been handled "
            "separately. Do not mention bill-routing services here. "
            "Every recommendation MUST include: "
            "id, urgency, headline, card, impact, impactWindow, body, trace. "
            "trace MUST be an array of objects with agent and detail.",
            {
                "strategy": strategy,
                "forecast": forecast,
            },
            {
                "recommendations": fallback
            }
        )

        # A model asked for {"recommendations": [...]} sometimes returns the
        # bare list instead. Both are honoured; anything else falls back rather
        # than crashing the run, because a malformed advisory response must not
        # take down figures that were computed without a model at all.
        if isinstance(result, dict):
            recommendations = result.get("recommendations", fallback)
        elif isinstance(result, list):
            recommendations = result
        else:
            recommendations = fallback
        if not isinstance(recommendations, list):
            recommendations = fallback

        # Guarantee frontend contract
        for i, rec in enumerate(recommendations):
            if not isinstance(rec, dict):
                continue
            rec.setdefault("id", f"rec-{i}")

            rec.setdefault(
                "urgency",
                "this-week"
            )

            rec.setdefault(
                "card",
                None
            )

            rec.setdefault(
                "impact",
                0
            )

            rec.setdefault(
                "impactWindow",
                "per period"
            )

            rec.setdefault(
                "body",
                ""
            )

            rec.setdefault(
                "trace",
                [
                    {
                        "agent": "strategy",
                        "detail": "Recommendation generated from the deterministic strategy analysis."
                    }
                ]
            )

        # Setup actions are deterministic and must not be rewritten by the
        # model — they name a condition the terms actually state.
        # Routing advice last: it is context about spending that cannot move,
        # not an action competing with the ones that can.
        return [*self.setup_actions(strategy, wallet), *recommendations,
                *self.routing_actions(strategy)]
