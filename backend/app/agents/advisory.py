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

    def run(self, strategy, forecast, wallet):
        top=strategy["categories"][:3]
        fallback=[{"id":f"rec-{i}","urgency":"act-now" if i==0 else "this-week","headline":f"Review {x['category']} — {x['bestCard']} is the best available option","card":{"name":x['bestCard'],"last4":"0000"},"impact":x["unclaimed"],"impactWindow":"per period","body":f"The deterministic strategy simulation found ${x['unclaimed']:.2f} of potential reward value in {x['category']}. Use {x['bestCard']} where the applicable rule and cap allow it.","trace":[{"agent":"strategy","detail":f"Optimal value exceeds captured value by ${x['unclaimed']:.2f}."}]} for i,x in enumerate(top)]
        result = self.runtime.json(
            "Turn deterministic financial findings into concise imperative recommendations. "
            "Never invent figures. Return a JSON array named recommendations. "
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

        recommendations = result.get("recommendations", fallback)

        # Guarantee frontend contract
        for i, rec in enumerate(recommendations):
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
        return [*self.setup_actions(strategy, wallet), *recommendations]
