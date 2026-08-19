# CardSense on ADK

## Running an agent

```bash
cd backend && source .venv/bin/activate
PYTHONPATH=. \
GOOGLE_GENAI_USE_VERTEXAI=TRUE \
GOOGLE_CLOUD_PROJECT=your-project \
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

All five production stages are ADK nodes. Card Intelligence and Advisory also
retain standalone ADK `Agent` packages for `adk run`/`adk web`; the production
workflow uses `BaseAgent` adapters around the application implementations so
the ADK and fallback paths share persistence, validation and model fallbacks.
Three of the five stages are deterministic on purpose.

| Agent | Home | Why |
|---|---|---|
| Advisory | ADK node over shared Advisory implementation | Language over figures it is given |
| Card Intelligence | ADK node over shared Card Intelligence implementation | Document understanding and persisted terms |
| Ingestion | Deterministic ADK node | A fetch, a join and a group-by |
| Forecast | Deterministic ADK node | Arithmetic over history |
| Strategy | Deterministic ADK node | Every money figure originates here |

Wrapping the deterministic three as LLM agents would put a model underneath
numbers that must be reproducible, and would contradict the architecture's
second principle. They are tools the workflow calls, not agents that reason.

## Status

- ADK is the default FastAPI execution path for synchronous and asynchronous
  runs; the built-in orchestrator remains an explicit fallback.
- Card Intelligence persists due term refreshes to both wallet and global rule
  documents before Strategy executes.
- Forecast consumes Strategy's measured leakage, matching the fallback output.
- Advisory uses the same replacement/suppression/expiry lifecycle as the
  fallback and publishes only current-run recommendations.
- Every node records queued/running/ok/degraded/failed telemetry with its real
  reads, writes and duration.

## The pipeline

`adk_agents/pipeline` composes all five agents as one graph:

```
    ingestion -> card_intelligence -> strategy -> forecast -> advisory
```

Forecast follows Strategy because its cost-of-inaction calculation consumes
the measured reward leakage. The former parallel graph omitted that input and
could not be output-compatible with the fallback.

The three deterministic agents are `BaseAgent` subclasses, not tools. A tool is
something a model chooses to call; these always run, in order, and handing that
decision to a planner would let the same inputs produce different figures on
different runs. Each delegates to the existing implementation in `app/agents/`,
so there is one copy of the logic and the two paths cannot drift.

```bash
PYTHONPATH=. GOOGLE_GENAI_USE_VERTEXAI=TRUE \
GOOGLE_CLOUD_PROJECT=your-project \
GOOGLE_CLOUD_LOCATION=global \
adk run adk_agents/pipeline "Run the CardSense analysis for demo-user."
```

The live Firestore demo path has been exercised end to end: ingestion reports
coverage, Card Intelligence reads terms, Strategy prices the wallet, Forecast
projects it, and Advisory is allowed to abstain when the measured gain is too
small to justify a recommendation.

## Running it from the API

`POST /api/v1/runs` takes an optional `engine`:

```bash
curl -X POST localhost:8080/api/v1/runs -H 'Content-Type: application/json' -d '{"engine":"adk"}'
```

`PIPELINE_ENGINE` defaults to `adk`. Set it to `orchestrator` for the fallback.
Keeping both paths makes rollback immediate, while parity tests prevent their
financial output and persistence contracts from drifting.

Both write the same read model. Run one then the other and the figures match to
the cent — spend, captured and unclaimed — which is what makes the switch safe:
it is not observable to a user.

Each node's output is written to `agent_runs` as it happens, tagged
`engine: "adk"`, so the activity page shows real stages and timings. The
deterministic nodes are normally much faster than document extraction, which
is one reason financial arithmetic remains outside the language model.

## Verification

`tests/test_adk_parity.py` starts both engines from identical stores and checks
the financial snapshot, card-rule refreshes, advice lifecycle, telemetry,
async selection and failure persistence.

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest tests/test_adk_parity.py -q
python -m evals.run_agent_evals
```

The golden evaluation currently passes 15 cases and 70 assertions across the
five production stages without calling Plaid or Gemini. Live model extraction
remains a separate, credentialed and potentially billable release check via
`python -m evals.run_extraction_eval`.
