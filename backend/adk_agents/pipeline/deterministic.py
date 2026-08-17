"""ADK adapters for the five production CardSense stages.

The graph owns scheduling and lifecycle; the existing application agents own
the work.  That division is what makes the ADK and orchestrator paths produce
the same persisted read model instead of maintaining a second implementation.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, AsyncGenerator, ClassVar

from google.adk import Event
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext

from app.orchestrator import Orchestrator
from app.simulation import plan as build_plan
from app.store import store


def _note(agent: BaseAgent, text: str) -> Event:
    from google.genai import types

    return Event(
        author=agent.name,
        content=types.Content(role="model", parts=[types.Part(text=text)]),
    )


class PipelineStage(BaseAgent):
    """One observable ADK node with orchestrator-compatible telemetry."""

    uid: str = "demo-user"
    run_id: str = ""
    active_orchestrator: Any = None

    agent_id: ClassVar[str]
    label: ClassVar[str]
    writes: ClassVar[Any]
    reads: ClassVar[list[str]]
    state_key: ClassVar[str]

    def _orchestrator(self) -> Orchestrator:
        return self.active_orchestrator or Orchestrator(store)

    def _execute(self, orchestrator: Orchestrator) -> tuple[Any, str, list[str]]:
        raise NotImplementedError

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        orchestrator = self._orchestrator()
        started = perf_counter()
        if self.run_id:
            orchestrator._start_stage(
                self.uid, self.run_id, self.agent_id, self.label,
                self.writes, self.reads, engine="adk",
            )
        try:
            with orchestrator.model_context(
                self.uid, self.run_id or None, self.agent_id,
            ):
                result, summary, degraded = self._execute(orchestrator)
            ctx.session.state[self.state_key] = result
            if self.run_id:
                orchestrator._log(
                    self.uid, self.run_id, self.agent_id, self.label,
                    self.writes, self.reads, degraded,
                    round((perf_counter() - started) * 1000), summary,
                    engine="adk",
                )
            yield _note(self, summary)
        except Exception as exc:
            if self.run_id:
                orchestrator.store.write_agent_run(
                    self.uid,
                    f"{self.run_id}-{self.agent_id}",
                    {
                        "id": f"{self.run_id}-{self.agent_id}",
                        "runId": self.run_id,
                        "agent": self.agent_id,
                        "label": self.label,
                        "status": "failed",
                        "startedAt": orchestrator._now(),
                        "durationMs": round((perf_counter() - started) * 1000),
                        "summary": f"{self.label} failed.",
                        "detail": str(exc)[:300],
                        "writes": self.writes,
                        "reads": self.reads,
                        "retryable": True,
                        "engine": "adk",
                    },
                )
            raise


class IngestionNode(PipelineStage):
    """Normalise and audit the canonical transaction feed."""

    agent_id: ClassVar[str] = "ingestion"
    label: ClassVar[str] = "Ingestion"
    writes: ClassVar[str] = "transactions"
    reads: ClassVar[list[str]] = ["plaid_items"]
    state_key: ClassVar[str] = "ingestion"

    def _execute(self, orchestrator: Orchestrator):
        result = orchestrator.ingestion.run(self.uid, orchestrator.store)
        summary = (
            f"{result['purchases']} posted purchases from {result['total']} transactions; "
            f"{result['mccCoverage']:.0%} carry a merchant category code."
        )
        return result, summary, orchestrator.ingestion.degraded(result)


class CardIntelligenceNode(PipelineStage):
    """Refresh due issuer terms and persist the resulting wallet/global rules."""

    agent_id: ClassVar[str] = "card-intelligence"
    label: ClassVar[str] = "Card intelligence"
    writes: ClassVar[str] = "card_rules"
    reads: ClassVar[list[str]] = ["wallet"]
    state_key: ClassVar[str] = "card_intelligence"
    refresh: bool = True

    def _execute(self, orchestrator: Orchestrator):
        wallet = orchestrator.store.get_wallet(self.uid)
        if self.refresh:
            wallet, reread, notes = orchestrator._recheck_due(self.uid, wallet)
            summary = (
                f"Reread {reread} of {len(wallet)} cards."
                if reread else "No cards were due a recheck."
            )
        else:
            reread, notes = 0, []
            summary = "Existing card rules retained during a deterministic account update."
        return {"wallet": wallet, "reread": reread}, summary, notes


class StrategyNode(PipelineStage):
    """Price wallet choices and persist the strategy run consumed downstream."""

    agent_id: ClassVar[str] = "strategy"
    label: ClassVar[str] = "Simulation & strategy"
    writes: ClassVar[str] = "strategy_runs"
    reads: ClassVar[list[str]] = ["transactions", "card_rules", "goal"]
    state_key: ClassVar[str] = "strategy"

    def _execute(self, orchestrator: Orchestrator):
        transactions = orchestrator.store.get_subcollection(self.uid, "transactions")
        wallet = orchestrator.store.get_wallet(self.uid)
        rules = orchestrator._rules(wallet)
        goal = orchestrator.store.get_user(self.uid).get("goal")
        result = orchestrator.strategy.run(transactions, wallet, rules, goal)
        result["goal"] = orchestrator.strategy.goal_projection(goal, result["captured"])
        if self.run_id:
            orchestrator.store.set_subdoc(self.uid, "strategy_runs", self.run_id, result)
        summary = "Simulation & strategy completed."
        return result, summary, result.get("degraded") or []


class ForecastNode(PipelineStage):
    """Project spending using the same strategy-derived leakage as production."""

    agent_id: ClassVar[str] = "forecast"
    label: ClassVar[str] = "Forecast"
    writes: ClassVar[str] = "forecasts"
    reads: ClassVar[list[str]] = [
        "transactions", "planned", "card_rules", "strategy_runs",
    ]
    state_key: ClassVar[str] = "forecast"

    def _execute(self, orchestrator: Orchestrator):
        transactions = orchestrator.store.get_subcollection(self.uid, "transactions")
        wallet = orchestrator.store.get_wallet(self.uid)
        rules = orchestrator._rules(wallet)
        strategy = (
            orchestrator.store.get_subdoc(self.uid, "strategy_runs", self.run_id)
            if self.run_id else None
        ) or {"unclaimed": 0}
        result = orchestrator.forecast.run(
            transactions,
            orchestrator.store.get_subcollection(self.uid, "planned"),
            wallet,
            rules,
            leakage_rate=orchestrator._leakage_rate(
                transactions, strategy.get("unclaimed", 0),
            ),
        )
        if self.run_id:
            orchestrator.store.set_subdoc(self.uid, "forecasts", self.run_id, result)
        summary = (
            f"Projected {result['projectedSpend']:.2f} over {result['horizonDays']} days "
            f"from {result['historyDays']} days of history and "
            f"{result['plannedSpend']:.2f} declared spend."
        )
        return result, summary, orchestrator.forecast.degraded(result)


class AdvisoryNode(PipelineStage):
    """Generate and persist the same recommendation lifecycle as production."""

    agent_id: ClassVar[str] = "advisory"
    label: ClassVar[str] = "Advisory"
    writes: ClassVar[str] = "advice"
    reads: ClassVar[list[str]] = ["strategy_runs", "forecasts", "advice"]
    state_key: ClassVar[str] = "advisory"
    refresh: bool = True

    def _execute(self, orchestrator: Orchestrator):
        if not self.refresh:
            expired = orchestrator._expire_open_advice(self.uid, self.run_id)
            summary = "No current recommendations were published for this run."
            detail = (
                "Advice generation was skipped after strategy changed; "
                f"{expired} open recommendation(s) were expired rather than retained as current."
            )
            return {"published": 0, "expired": expired}, summary, [detail]

        transactions = orchestrator.store.get_subcollection(self.uid, "transactions")
        wallet = orchestrator.store.get_wallet(self.uid)
        rules = orchestrator._rules(wallet)
        strategy = orchestrator.store.get_subdoc(
            self.uid, "strategy_runs", self.run_id,
        ) or {"categories": [], "routable": []}
        forecast = orchestrator.store.get_subdoc(
            self.uid, "forecasts", self.run_id,
        ) or {}
        welcome_now, _ = orchestrator._welcome(
            self.uid, wallet, transactions, forecast,
        )
        plan = build_plan(
            orchestrator.strategy,
            transactions,
            wallet,
            rules,
            orchestrator.store.get_subcollection(self.uid, "catalog"),
            strategy.get("routable", []),
            welcome_now,
            service_id=strategy.get("routingService"),
        )
        advice = orchestrator.advisory.run(
            strategy, forecast, wallet, welcome_now, plan,
        )
        published, expired, suppressed = orchestrator._replace_advice(
            self.uid, self.run_id, advice,
        )
        summary = (
            f"Published {published} recommendations for this run; "
            f"expired {expired} stale and preserved {suppressed} resolved outcomes."
        )
        return {
            "published": published,
            "expired": expired,
            "suppressed": suppressed,
        }, summary, []
