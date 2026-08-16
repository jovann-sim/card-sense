"""Executing the ADK graph from inside the API.

This is what lets the FastAPI service run the pipeline as a graph rather than
as a hand-rolled sequence, while keeping the existing orchestrator intact as a
fallback. Both write the same read model, so the interface cannot tell which
engine produced a snapshot — which is the point: switching engines must not be
observable to a user.

Every node records its own lifecycle to `agent_runs`, so queued, running,
degraded and failed states match the built-in orchestrator.
"""

from __future__ import annotations

import asyncio
import uuid

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

APP_NAME = "cardsense"

# Which graph node corresponds to which agent id in the read model. The
# activity page groups by these, so they must match the orchestrator's.
NODE_TO_AGENT = {
    "ingestion": "ingestion",
    "forecast": "forecast",
    "card_intelligence_agent": "card-intelligence",
    "strategy": "strategy",
    "advisory_agent": "advisory",
}

async def _run(
    uid: str,
    request: str,
    *,
    run_id: str | None = None,
    active_orchestrator=None,
    refresh_advice: bool = True,
    refresh_card_intelligence: bool = True,
) -> tuple[str, dict]:
    from adk_agents.pipeline.agent import build_pipeline

    run_id = run_id or uuid.uuid4().hex
    # The graph is built per run so its nodes persist under this run id, which
    # is what the projection reads when it assembles the snapshot.
    pipeline = build_pipeline(
        uid=uid,
        run_id=run_id,
        active_orchestrator=active_orchestrator,
        refresh_advice=refresh_advice,
        refresh_card_intelligence=refresh_card_intelligence,
    )
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=APP_NAME, user_id=uid)
    runner = Runner(agent=pipeline, app_name=APP_NAME, session_service=session_service)

    async for _event in runner.run_async(
        user_id=uid,
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=request)]),
    ):
        pass

    final = await session_service.get_session(app_name=APP_NAME, user_id=uid, session_id=session.id)
    return run_id, dict(getattr(final, "state", {}) or {})


def run_pipeline(
    uid: str,
    request: str = "Run the CardSense analysis.",
    *,
    run_id: str | None = None,
    active_orchestrator=None,
    refresh_advice: bool = True,
    refresh_card_intelligence: bool = True,
) -> tuple[str, dict]:
    """Run the graph and return its id and final state.

    Synchronous by design: the caller is a FastAPI endpoint that already blocks
    on Firestore, and an event loop per request is simpler to reason about than
    threading an async orchestrator through the whole service.
    """
    return asyncio.run(_run(
        uid,
        request,
        run_id=run_id,
        active_orchestrator=active_orchestrator,
        refresh_advice=refresh_advice,
        refresh_card_intelligence=refresh_card_intelligence,
    ))
