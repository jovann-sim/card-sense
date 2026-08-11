# CardSense on ADK

## Running an agent

```bash
cd backend && source .venv/bin/activate
PYTHONPATH=. \
GOOGLE_GENAI_USE_VERTEXAI=TRUE \
GOOGLE_CLOUD_PROJECT=project-cc11421f-7c37-404f-a7e \
GOOGLE_CLOUD_LOCATION=global \
adk run adk_agents/card_intelligence "your query"
```

`PYTHONPATH=.` matters: ADK loads an agent folder without the backend on the
path, so any agent importing from `app` fails with `No module named 'app'`
without it.

Omit the query for an interactive session. `adk web adk_agents` gives a browser
UI over every agent in this directory, which is the better demo surface.

Those three environment variables are what point ADK at Vertex rather than an
AI Studio key. They mirror what `app/config.py` already reads.

## Layout

ADK discovers agents by folder: each subdirectory is an agent package whose
`__init__.py` imports `agent`, and whose `agent.py` exposes `root_agent`.

```
adk_agents/
  advisory/
    __init__.py   from . import agent
    agent.py      root_agent = Agent(...)
```

## Which agents belong here, and which do not

Only the two Gemini-driven agents become ADK `Agent`s. ADK's `Agent` is
LLM-shaped — it takes a model and an instruction — and three of the five
CardSense agents are deterministic on purpose.

| Agent | Home | Why |
|---|---|---|
| Advisory | ADK agent | Language over figures it is given |
| Card Intelligence | ADK agent | Document understanding |
| Ingestion | Plain Python, exposed as a tool | A fetch, a join and a group-by |
| Forecast | Plain Python, exposed as a tool | Arithmetic over history |
| Strategy | Plain Python, exposed as a tool | Every money figure originates here |

Wrapping the deterministic three as LLM agents would put a model underneath
numbers that must be reproducible, and would contradict the architecture's
second principle. They are tools the workflow calls, not agents that reason.

## Status

- **Advisory** runs standalone and returns recommendations from supplied
  figures, without recomputing them.
- **Card intelligence** runs standalone with a fetch tool and a schema-
  constrained result. Verified on both paths that matter: given a real document
  it extracts the full structure at 0.9 confidence, and asked about a card it
  demonstrably knows from training with no document supplied, it returns
  `{"rules": [], "confidence": 0}` rather than reciting one.
- The FastAPI orchestrator remains the live path. Do not remove it until the
  ADK pipeline is proven end to end.

## The pipeline

`adk_agents/pipeline` composes all five agents as one graph:

```
ingestion ─┬─> card_intelligence ─┐
           └─> forecast ──────────┴─> strategy ─> advisory
```

Card intelligence and forecast do not depend on each other, so the graph runs
them concurrently. Strategy waits for both, because it prices what was ingested
against the rules that were read.

The three deterministic agents are `BaseAgent` subclasses, not tools. A tool is
something a model chooses to call; these always run, in order, and handing that
decision to a planner would let the same inputs produce different figures on
different runs. Each delegates to the existing implementation in `app/agents/`,
so there is one copy of the logic and the two paths cannot drift.

```bash
PYTHONPATH=. GOOGLE_GENAI_USE_VERTEXAI=TRUE \
GOOGLE_CLOUD_PROJECT=project-cc11421f-7c37-404f-a7e \
GOOGLE_CLOUD_LOCATION=global \
adk run adk_agents/pipeline "Run the CardSense analysis for demo-user."
```

Verified end to end against live Firestore: ingestion reported coverage,
card intelligence read a real terms document, strategy priced the wallet, and
advisory declined to invent advice when the gap was $0.16 — "less than a dollar
a month" — which is the restraint the instruction asks for.

## Next

- Switch the FastAPI orchestrator to call the workflow, keeping the current
  path until the new one is proven.
- Persist workflow runs to `agent_runs` so the activity page shows ADK stages.
