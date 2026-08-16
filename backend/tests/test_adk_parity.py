from __future__ import annotations

from copy import deepcopy
from datetime import date

from fastapi import BackgroundTasks
import pytest

from adk_agents.pipeline.runner import run_pipeline
from app import main
from app.demo_data import generate
from app.models import RunIn
from app.orchestrator import AGENTS, Orchestrator
from app.store import Store


UID = "parity-user"


def populated_store() -> Store:
    store = Store()
    for row in generate(today=date.today(), months=4, account_ids=["acct"]):
        store.set_subdoc(UID, "transactions", row["id"], row)

    rules = [
        {"id": "groceries", "categoryLabel": "Groceries", "rate": "5%", "valuePerDollar": 0.05},
        {"id": "dining", "categoryLabel": "Dining", "rate": "3%", "valuePerDollar": 0.03},
        {"id": "base", "categoryLabel": "Everything else", "rate": "1%", "valuePerDollar": 0.01},
    ]
    source = {
        "label": "Issuer terms", "locator": "entered by test",
        "retrievedAt": str(date.today()),
    }
    store.set_global_doc("card_rules", "test-card", {
        "rules": rules,
        "characteristics": {},
        "source": source,
        "status": "parsed",
        "confidence": 1,
    })
    store.set_subdoc(UID, "wallet", "test-card", {
        "cardId": "test-card", "name": "Test Card", "last4": "1234",
        "network": "Visa", "annualFee": 0, "track": "cashback",
        "accountId": "acct", "parseStatus": "parsed", "parseConfidence": 1,
        "rules": rules, "source": source, "recheckCadence": "weekly",
        "nextRecheckAt": "2099-01-01", "termsUrl": None,
    })
    store.set_subdoc(UID, "advice", "stale", {
        "id": "stale", "runId": "older-run", "outcome": "open",
        "headline": "Advice no longer supported", "card": None,
        "impact": 9, "predicted": 9, "impactWindow": "per period",
        "window": "per period", "pushedAt": "2026-01-01T00:00:00+00:00",
        "urgency": "this-week", "body": "Old advice.", "trace": [],
    })
    return store


def advice_view(store: Store) -> list[dict]:
    return sorted(
        [
            {
                "id": row.get("id"),
                "outcome": row.get("outcome"),
                "headline": row.get("headline"),
                "card": row.get("card"),
                "impact": row.get("impact"),
                "invalidated": bool(row.get("invalidatedByRunId")),
                "gapReason": row.get("gapReason"),
            }
            for row in store.get_subcollection(UID, "advice")
        ],
        key=lambda row: row["id"],
    )


def telemetry_view(store: Store, run_id: str) -> list[dict]:
    order = {agent: index for index, (agent, _label) in enumerate(AGENTS)}
    rows = [
        row for row in store.get_subcollection(UID, "agent_runs")
        if row.get("runId") == run_id
    ]
    rows.sort(key=lambda row: order[row["agent"]])
    return [
        {
            key: row.get(key)
            for key in ("agent", "status", "summary", "detail", "writes", "reads", "retryable")
        }
        for row in rows
    ]


def test_adk_matches_orchestrator_read_model_persistence_and_lifecycle():
    orchestrator_store = populated_store()
    adk_store = Store()
    adk_store.memory = deepcopy(orchestrator_store.memory)
    orchestrator = Orchestrator(orchestrator_store)
    adk_orchestrator = Orchestrator(adk_store)

    orchestrator_run, orchestrator_snapshot = orchestrator.run(UID, "parity")
    adk_run, _ = run_pipeline(
        UID, "parity", active_orchestrator=adk_orchestrator,
    )
    adk_snapshot = adk_orchestrator.project(UID, adk_run)

    for key in (
        "totals", "categories", "cards", "forecast", "goal", "plan",
        "routable", "welcome", "welcomeCandidates", "catalog",
    ):
        assert adk_snapshot[key] == orchestrator_snapshot[key], key

    assert advice_view(adk_store) == advice_view(orchestrator_store)
    assert adk_snapshot["trackRecord"] | {"records": []} == (
        orchestrator_snapshot["trackRecord"] | {"records": []}
    )
    assert telemetry_view(adk_store, adk_run) == telemetry_view(
        orchestrator_store, orchestrator_run,
    )
    assert {row.get("engine") for row in adk_store.get_subcollection(UID, "agent_runs")} == {"adk"}


class DueCardIntelligence:
    def due_for_recheck(self, _card):
        return True

    def parse(self, _card, _previous):
        return {
            "rules": [{"id": "new", "categoryLabel": "Dining", "rate": "4%"}],
            "characteristics": {"issuer": "Test Bank"},
            "source": {"label": "Fresh terms", "locator": "test", "retrievedAt": "2026-08-16"},
            "recheckCadence": "weekly", "nextRecheckAt": "2026-08-23",
            "status": "parsed", "note": None, "confidence": 0.9,
            "failureReason": None,
        }


def test_adk_card_intelligence_persists_due_rule_refreshes():
    store = populated_store()
    store.set_subdoc(UID, "wallet", "test-card", {
        "termsUrl": "https://example.test/terms", "nextRecheckAt": "2020-01-01",
    })
    orchestrator = Orchestrator(store)
    orchestrator.cardintel = DueCardIntelligence()

    run_id, _ = run_pipeline(UID, "refresh", active_orchestrator=orchestrator)

    wallet = store.get_subdoc(UID, "wallet", "test-card")
    global_rules = store.get_global_doc("card_rules", "test-card")
    assert wallet["rules"][0]["rate"] == "4%"
    assert wallet["source"]["label"] == "Fresh terms"
    assert global_rules["rules"] == wallet["rules"]
    card_run = store.get_subdoc(UID, "agent_runs", f"{run_id}-card-intelligence")
    assert card_run["status"] == "ok"
    assert card_run["engine"] == "adk"
    assert card_run["summary"] == "Reread 1 of 1 cards."


def test_async_run_queues_the_selected_adk_engine(monkeypatch):
    store = Store()
    orchestrator = Orchestrator(store)
    background = BackgroundTasks()
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "orch", orchestrator)

    response = main.start_agent_run(RunIn(engine="adk"), background)

    assert response["engine"] == "adk"
    assert {row["engine"] for row in store.get_subcollection(main.UID, "agent_runs")} == {"adk"}
    assert len(background.tasks) == 1
    assert background.tasks[0].args[-1] == "adk"


def test_async_adk_execution_projects_and_persists_the_snapshot():
    store = Store()
    orchestrator = Orchestrator(store)

    main._execute_background_run(
        orchestrator, "async-adk-run", "run in background", "adk",
    )

    snapshot = store.get_snapshot(main.UID)
    assert snapshot is not None
    assert store.get_user(main.UID)["lastRunId"] == "async-adk-run"
    runs = [
        row for row in store.get_subcollection(main.UID, "agent_runs")
        if row.get("runId") == "async-adk-run"
    ]
    assert len(runs) == len(AGENTS)
    assert {row["engine"] for row in runs} == {"adk"}
    assert {row["status"] for row in runs} <= {"ok", "degraded"}


def test_adk_failure_is_persisted_for_run_polling():
    store = Store()
    orchestrator = Orchestrator(store)

    def fail_ingestion(*_args):
        raise RuntimeError("input audit failed")

    orchestrator.ingestion.run = fail_ingestion

    with pytest.raises(RuntimeError, match="input audit failed"):
        run_pipeline(UID, "fail", run_id="failed-run", active_orchestrator=orchestrator)

    failed = store.get_subdoc(UID, "agent_runs", "failed-run-ingestion")
    assert failed["status"] == "failed"
    assert failed["engine"] == "adk"
    assert failed["retryable"] is True
    assert failed["detail"] == "input audit failed"
