"""The whole CardSense pipeline as one ADK graph.

Five agents, three of them deterministic, wired as a fixed graph rather than a
model deciding what to call next. That distinction is the architecture: the
order in which spending is read, priced and explained is not a judgement call,
and handing it to a planner would make the same inputs produce different
figures on different runs.

    ingestion ─┬─> card_intelligence ─┐
               └─> forecast ──────────┴─> strategy ─> advisory

Card intelligence and forecast are independent of each other, so the graph runs
them concurrently. Strategy waits for both because it prices what was ingested
against the rules that were read.
"""

from google.adk import Workflow

from adk_agents.advisory.agent import root_agent as advisory_agent
from adk_agents.card_intelligence.agent import root_agent as card_intelligence_agent
from adk_agents.pipeline.deterministic import ForecastNode, IngestionNode, StrategyNode

ingestion = IngestionNode(
    name="ingestion",
    description="Normalises the transaction feed and reports coverage.",
)
forecast = ForecastNode(
    name="forecast",
    description="Projects near-term spending and the dates the best card changes.",
)
strategy = StrategyNode(
    name="strategy",
    description="Prices every card against actual spending.",
)

root_agent = Workflow(
    name="cardsense_pipeline",
    description="Reads spending and card terms, prices one against the other, and explains the gap.",
    # Each tuple is a path, so consecutive pairs become edges. The fan-out is
    # written as separate edges from ingestion rather than two paths through
    # it, which would declare START -> ingestion twice.
    edges=[
        ("START", ingestion),
        (ingestion, card_intelligence_agent),
        (ingestion, forecast),
        (card_intelligence_agent, strategy),
        (forecast, strategy),
        (strategy, advisory_agent),
    ],
)
