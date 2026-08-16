"""The whole CardSense pipeline as one ADK graph.

Five production stages wired as a fixed ADK graph rather than a model deciding
what to call next. Each ADK node delegates to the same application agent used
by the built-in orchestrator, so persistence and financial output stay equal.

    ingestion -> card_intelligence -> strategy -> forecast -> advisory

Forecast follows strategy because its cost-of-inaction figure uses the measured
reward leakage. Running it in parallel would silently produce a different
forecast from the authoritative path.
"""

from google.adk import Workflow

from adk_agents.pipeline.deterministic import (
    AdvisoryNode,
    CardIntelligenceNode,
    ForecastNode,
    IngestionNode,
    StrategyNode,
)

def build_pipeline(
    uid: str = "demo-user",
    run_id: str = "",
    *,
    active_orchestrator=None,
    refresh_advice: bool = True,
    refresh_card_intelligence: bool = True,
) -> Workflow:
    """A graph bound to one run, so nodes persist where the projection looks.

    The module-level `root_agent` below is the same graph without a run id,
    which is what `adk run` and `adk web` load for interactive use.
    """
    common = {"uid": uid, "run_id": run_id, "active_orchestrator": active_orchestrator}
    ingest = IngestionNode(name="ingestion", **common,
                           description="Normalises the transaction feed and reports coverage.")
    cardintel = CardIntelligenceNode(
        name="card_intelligence_agent", refresh=refresh_card_intelligence, **common,
        description="Refreshes due issuer terms and persists verified reward rules.",
    )
    strat = StrategyNode(name="strategy", **common,
                         description="Prices every card against actual spending.")
    fore = ForecastNode(name="forecast", **common,
                        description="Projects spending using measured reward leakage.")
    advisory = AdvisoryNode(
        name="advisory_agent", refresh=refresh_advice, **common,
        description="Publishes deterministic and safely worded recommendations.",
    )
    return Workflow(
        name="cardsense_pipeline",
        description="Reads spending and card terms, prices one against the other, and explains the gap.",
        edges=[
            ("START", ingest),
            (ingest, cardintel),
            (cardintel, strat),
            (strat, fore),
            (fore, advisory),
        ],
    )


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
card_intelligence = CardIntelligenceNode(
    name="card_intelligence_agent",
    description="Refreshes due issuer terms and persists verified reward rules.",
)
advisory = AdvisoryNode(
    name="advisory_agent",
    description="Publishes deterministic and safely worded recommendations.",
)

root_agent = Workflow(
    name="cardsense_pipeline",
    description="Reads spending and card terms, prices one against the other, and explains the gap.",
    # Each tuple is a path, so consecutive pairs become edges. The fan-out is
    # written as separate edges from ingestion rather than two paths through
    # it, which would declare START -> ingestion twice.
    edges=[
        ("START", ingestion),
        (ingestion, card_intelligence),
        (card_intelligence, strategy),
        (strategy, forecast),
        (forecast, advisory),
    ],
)
