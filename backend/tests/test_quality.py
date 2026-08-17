from __future__ import annotations

from app import main
from app.quality import build_quality_report
from app.store import Store


UID = "quality-user"
AGENTS = ("ingestion", "card-intelligence", "strategy", "forecast", "advisory")


def add_run(store: Store, run_id: str, statuses: list[str], durations: list[int], engine="adk"):
    for agent, status, duration in zip(AGENTS, statuses, durations, strict=True):
        store.set_subdoc(UID, "agent_runs", f"{run_id}-{agent}", {
            "runId": run_id,
            "agent": agent,
            "status": status,
            "durationMs": duration,
            "engine": engine,
        })


def test_quality_report_persists_the_current_golden_suite():
    store = Store()

    first = build_quality_report(store, UID)
    second = build_quality_report(store, UID)

    assert first["golden"]["passed"] is True
    assert first["golden"]["casesPassed"] == first["golden"]["casesTotal"] == 15
    assert first["golden"]["assertionsPassed"] == first["golden"]["assertionsTotal"] == 70
    assert first["golden"]["unsupportedClaims"] == 0
    assert second["golden"]["evaluatedAt"] == first["golden"]["evaluatedAt"]
    assert len(store.get_subcollection(UID, "quality_reports")) == 1


def test_quality_report_measures_real_runs_at_run_and_agent_level():
    store = Store()
    add_run(store, "healthy", ["ok"] * 5, [10, 20, 30, 40, 50])
    add_run(store, "degraded", ["ok", "degraded", "ok", "ok", "ok"], [20] * 5)
    # A failed pipeline can stop before all five stages; it is still terminal.
    store.set_subdoc(UID, "agent_runs", "failed-ingestion", {
        "runId": "failed", "agent": "ingestion", "status": "failed",
        "durationMs": 50, "engine": "adk",
    })

    report = build_quality_report(store, UID)

    assert report["live"] == {
        "runsObserved": 3,
        "terminalRuns": 3,
        "degradedRuns": 1,
        "failedRuns": 1,
        "degradedRate": 0.3333,
        "failedRate": 0.3333,
        "medianRunDurationMs": 100.0,
        "engines": {"adk": 3},
        "agents": [
            {"id": "ingestion", "executions": 3, "degraded": 0, "failed": 1, "medianDurationMs": 20.0},
            {"id": "card-intelligence", "executions": 2, "degraded": 1, "failed": 0, "medianDurationMs": 20.0},
            {"id": "strategy", "executions": 2, "degraded": 0, "failed": 0, "medianDurationMs": 25.0},
            {"id": "forecast", "executions": 2, "degraded": 0, "failed": 0, "medianDurationMs": 30.0},
            {"id": "advisory", "executions": 2, "degraded": 0, "failed": 0, "medianDurationMs": 35.0},
        ],
    }


def test_quality_report_does_not_invent_outcome_accuracy_or_model_cost():
    store = Store()
    store.set_subdoc(UID, "advice", "measured", {"predicted": 10.0, "actual": 8.0})
    store.set_subdoc(UID, "advice", "open", {"predicted": 20.0})

    measured = build_quality_report(store, UID)
    empty = build_quality_report(Store(), UID)

    assert measured["outcomes"]["status"] == "measured"
    assert measured["outcomes"]["evaluated"] == 1
    assert measured["outcomes"]["meanAbsoluteError"] == 2.0
    assert empty["outcomes"]["status"] == "not-measured"
    assert empty["outcomes"]["meanAbsoluteError"] is None
    assert measured["modelCost"]["status"] == "not-measured"
    assert measured["modelCost"]["estimatedUsd"] is None


def test_quality_endpoint_uses_the_active_application_store(monkeypatch):
    store = Store()
    monkeypatch.setattr(main, "store", store)

    report = main.agent_quality()

    assert report["golden"]["passed"] is True
    assert store.get_subdoc(main.UID, "quality_reports", "golden-latest") is not None

