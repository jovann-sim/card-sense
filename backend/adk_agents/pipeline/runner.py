"""Executing the ADK graph from inside the API.

This is what lets the FastAPI service run the pipeline as a graph rather than
as a hand-rolled sequence, while keeping the existing orchestrator intact as a
fallback. Both write the same read model, so the interface cannot tell which
engine produced a snapshot — which is the point: switching engines must not be
observable to a user.

Every node's output is recorded to `agent_runs` as it happens, so the activity
page shows real ADK stages with real timings rather than a summary written
after the fact.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from time import perf_counter

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.store import store

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

AGENT_WRITES = {
    "ingestion": "transactions",
    "forecast": "forecasts",
    "card-intelligence": "card_rules",
    "strategy": "strategy_runs",
    "advisory": "advice",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text_of(event) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    return " ".join(p.text for p in parts if getattr(p, "text", None)).strip()


async def _run(uid: str, request: str) -> tuple[str, dict]:
    from adk_agents.pipeline.agent import build_pipeline

    run_id = uuid.uuid4().hex
    # The graph is built per run so its nodes persist under this run id, which
    # is what the projection reads when it assembles the snapshot.
    pipeline = build_pipeline(uid=uid, run_id=run_id)
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=APP_NAME, user_id=uid)
    runner = Runner(agent=pipeline, app_name=APP_NAME, session_service=session_service)

    started = perf_counter()
    seen: set[str] = set()

    async for event in runner.run_async(
        user_id=uid,
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=request)]),
    ):
        author = getattr(event, "author", None)
        agent_id = NODE_TO_AGENT.get(author)
        if not agent_id or agent_id in seen:
            continue

        summary = _text_of(event)
        if not summary:
            continue

        seen.add(agent_id)
        elapsed = round((perf_counter() - started) * 1000)
        store.write_agent_run(uid, f"{run_id}-{agent_id}", {
            "id": f"{run_id}-{agent_id}",
            "runId": run_id,
            "agent": agent_id,
            "status": "ok",
            "startedAt": _now(),
            "durationMs": elapsed,
            # The node's own account of what it did, not a description written
            # for it afterwards.
            "summary": summary[:400],
            "detail": None,
            "writes": AGENT_WRITES.get(agent_id, ""),
            "reads": [],
            "retryable": False,
            "engine": "adk",
        })

    final = await session_service.get_session(app_name=APP_NAME, user_id=uid, session_id=session.id)
    return run_id, dict(getattr(final, "state", {}) or {})


def run_pipeline(uid: str, request: str = "Run the CardSense analysis.") -> tuple[str, dict]:
    """Run the graph and return its id and final state.

    Synchronous by design: the caller is a FastAPI endpoint that already blocks
    on Firestore, and an event loop per request is simpler to reason about than
    threading an async orchestrator through the whole service.
    """
    return asyncio.run(_run(uid, request))
