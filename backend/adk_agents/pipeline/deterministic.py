"""The three CardSense agents that must never involve a language model.

They are real nodes in the ADK graph rather than tools, because they are not
things a model chooses to call — they always run, in order, and their output is
the input to what follows. Making them tools would hand a model the decision of
whether spending gets counted.

Each subclasses BaseAgent and delegates to the existing implementation, so
there is one copy of the logic and the FastAPI path and the ADK path cannot
drift apart.
"""

from __future__ import annotations

from typing import AsyncGenerator

from google.adk import Event
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext

from app.agents.forecast import ForecastAgent
from app.agents.ingestion import IngestionAgent
from app.agents.strategy import StrategyAgent
from app.store import store


def _note(agent: BaseAgent, text: str) -> Event:
    """A graph node still has to report what it did."""
    from google.genai import types

    return Event(
        author=agent.name,
        content=types.Content(role="model", parts=[types.Part(text=text)]),
    )


class IngestionNode(BaseAgent):
    """Normalises the transaction feed and reports its coverage."""

    uid: str = "demo-user"

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        summary = IngestionAgent().run(self.uid, store)
        ctx.session.state["ingestion"] = summary
        yield _note(
            self,
            f"{summary['purchases']} purchases from {summary['total']} transactions; "
            f"{summary['mccCoverage']:.0%} carry a merchant category code; "
            f"{summary['excluded']} excluded as transfers or payments.",
        )


class StrategyNode(BaseAgent):
    """Prices every card against actual spending. Every money figure starts here."""

    uid: str = "demo-user"

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        wallet = store.get_wallet(self.uid)
        rules = {
            card["cardId"]: (store.get_global_doc("card_rules", card["cardId"]) or {}).get("rules", [])
            for card in wallet
        }
        result = StrategyAgent().run(
            store.get_subcollection(self.uid, "transactions"),
            wallet,
            rules,
            store.get_user(self.uid).get("goal"),
        )
        ctx.session.state["strategy"] = result
        yield _note(
            self,
            f"Priced {len(wallet)} cards across {len(result['categories'])} categories: "
            f"{result['captured']:.2f} captured, {result['unclaimed']:.2f} unclaimed.",
        )


class ForecastNode(BaseAgent):
    """Projects near-term spending and the dates the right card changes."""

    uid: str = "demo-user"

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        wallet = store.get_wallet(self.uid)
        result = ForecastAgent().run(
            store.get_subcollection(self.uid, "transactions"),
            store.get_subcollection(self.uid, "planned"),
            wallet,
            {
                card["cardId"]: (store.get_global_doc("card_rules", card["cardId"]) or {}).get("rules", [])
                for card in wallet
            },
        )
        ctx.session.state["forecast"] = result
        yield _note(
            self,
            f"Projected {result['projectedSpend']:.2f} over {result['horizonDays']} days "
            f"across {len(result.get('timeline', []))} dated events.",
        )
