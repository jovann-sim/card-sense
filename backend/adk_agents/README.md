# CardSense on ADK

## Running an agent

```bash
cd backend && source .venv/bin/activate
GOOGLE_GENAI_USE_VERTEXAI=TRUE \
GOOGLE_CLOUD_PROJECT=project-cc11421f-7c37-404f-a7e \
GOOGLE_CLOUD_LOCATION=global \
adk run adk_agents/advisory "your query"
```

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

- Advisory runs standalone and returns recommendations from supplied figures.
- The FastAPI orchestrator remains the live path. Do not remove it until the
  ADK pipeline is proven end to end.
