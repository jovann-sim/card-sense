from __future__ import annotations
from .runtime import GeminiRuntime

class AdvisoryAgent:
    id="advisory"
    def __init__(self,runtime): self.runtime=runtime
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

        return recommendations
