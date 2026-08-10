from app.orchestrator import Orchestrator
from app.store import Store
from app.models import AdviceResolveIn, GoalIn, PlannedItemIn, Snapshot
from app import main


def test_snapshot_is_persisted_as_a_subcollection_read_model():
    store = Store()
    orchestrator = Orchestrator(store)
    run_id, snapshot = orchestrator.run("test-user")
    assert Snapshot.model_validate(snapshot)
    assert store.get_snapshot("test-user")["generatedAt"] == snapshot["generatedAt"]
    assert store.get_subdoc("test-user", "forecasts", run_id)
    assert store.get_subdoc("test-user", "strategy_runs", run_id)
    assert len(store.get_subcollection("test-user", "agent_runs")) == 5


def test_snapshot_cache_avoids_repeated_backing_store_reads(monkeypatch):
    store = Store()
    store.set_subdoc("test-user", "snapshots", "current", {"version": 1})
    original_get_subdoc = store.get_subdoc
    backing_reads = 0

    def counted_get_subdoc(*args, **kwargs):
        nonlocal backing_reads
        backing_reads += 1
        return original_get_subdoc(*args, **kwargs)

    monkeypatch.setattr(store, "get_subdoc", counted_get_subdoc)

    assert store.get_snapshot("test-user") == {"id": "current", "version": 1}
    assert store.get_snapshot("test-user") == {"id": "current", "version": 1}
    assert backing_reads == 1

    store.set_snapshot("test-user", {"version": 2})
    assert store.get_snapshot("test-user") == {"version": 2}
    assert backing_reads == 1


def test_planned_save_uses_targeted_snapshot_projection(monkeypatch):
    store = Store()
    orchestrator = Orchestrator(store)
    store.set_snapshot(main.UID, orchestrator.empty_snapshot(main.UID))

    def unexpected_advisory(*_args, **_kwargs):
        raise AssertionError("planned save must not invoke Advisory")

    orchestrator.advisory.run = unexpected_advisory
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "orch", orchestrator)

    snapshot = main.add_planned(PlannedItemIn(
        kind="purchase",
        label="Laptop",
        startDate="2026-09-01",
        amount=2000,
        categories=["Online retail"],
    ))

    assert snapshot["planned"][0]["label"] == "Laptop"
    assert snapshot["forecast"]["timeline"][0]["title"] == "Laptop"

    removed = main.delete_planned(snapshot["planned"][0]["id"])
    assert removed["planned"] == []
    assert removed["forecast"]["timeline"] == []
    assert store.get_subcollection(main.UID, "agent_runs") == []
    assert store.get_subcollection(main.UID, "forecasts") == []


def test_goal_save_skips_advisory_model_call(monkeypatch):
    store = Store()
    orchestrator = Orchestrator(store)

    def unexpected_advisory(*_args, **_kwargs):
        raise AssertionError("goal save must not invoke Advisory")

    orchestrator.advisory.run = unexpected_advisory
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "orch", orchestrator)

    snapshot = main.set_goal(GoalIn(
        track="miles",
        target=60_000,
        unitLabel="miles",
        current=1_000,
        deadline="2027-01-01",
        purpose="Tokyo",
    ))

    assert snapshot["goal"]["track"] == "miles"
    assert snapshot["goal"]["target"] == 60_000
    assert store.get_subcollection(main.UID, "agent_runs") == []
    assert store.get_subcollection(main.UID, "strategy_runs") == []


def test_track_record_tolerates_non_numeric_model_values():
    orchestrator = Orchestrator(Store())
    advice = [
        {
            "id": "bad-prediction",
            "outcome": "dismissed",
            "predicted": "Inaccurate or missing financial projections",
            "impact": "not a number",
        },
        {"id": "bad-actual", "outcome": "acted", "predicted": "12.5", "actual": None},
    ]

    record = orchestrator._track_record(advice)

    assert record["earned"] == 0
    assert record["missed"] == 0
    assert record["records"][0]["predicted"] == 0
    assert record["records"][1]["predicted"] == 12.5
    assert record["records"][1]["actual"] == 0
    assert orchestrator._recommendation(advice[0])["impact"] == 0


def test_advice_resolution_uses_targeted_snapshot_projection(monkeypatch):
    store = Store()
    orchestrator = Orchestrator(store)
    advice = {
        "id": "recommendation",
        "outcome": "open",
        "headline": "Use the better card",
        "urgency": "this-week",
        "card": None,
        "impact": 8,
        "impactWindow": "per period",
        "predicted": 8,
        "window": "per period",
        "body": "Save more.",
        "trace": [],
        "pushedAt": "2026-08-10T00:00:00+00:00",
    }
    store.set_subdoc(main.UID, "advice", advice["id"], advice)
    snapshot = orchestrator.empty_snapshot(main.UID)
    snapshot["recommendations"] = [orchestrator._recommendation(advice)]
    snapshot["trackRecord"] = orchestrator._track_record([advice])
    store.set_snapshot(main.UID, snapshot)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "orch", orchestrator)

    resolved = main.resolve_advice(
        advice["id"],
        AdviceResolveIn(outcome="dismissed"),
    )

    assert resolved["recommendations"] == []
    assert resolved["trackRecord"]["missed"] == 8
    assert resolved["trackRecord"]["records"][0]["outcome"] == "dismissed"
    assert store.get_subcollection(main.UID, "agent_runs") == []
    assert store.get_subcollection(main.UID, "strategy_runs") == []


def test_projection_exposes_degraded_card_and_goal_contract():
    store = Store()
    store.set_subdoc("user", "wallet", "card", {"cardId": "card", "name": "Unreadable", "last4": "1234", "network": "Visa", "annualFee": 0, "track": "cashback", "rules": [], "source": {"label": "terms", "locator": "test", "retrievedAt": "2026-01-01"}, "recheckCadence": "weekly", "nextRecheckAt": "2026-01-08", "parseStatus": "failed", "parseNote": "Could not read terms."})
    store.set_user("user", {"goal": {"track": "cashback", "target": None, "unitLabel": "dollars", "current": 0, "deadline": None, "purpose": ""}})
    _, snapshot = Orchestrator(store).run("user")
    assert snapshot["agents"][2]["status"] == "degraded"
    assert snapshot["cards"][0]["state"] == "unverified"
    assert snapshot["catalog"][0] == {
        "name": "Unreadable",
        "network": "Visa",
        "headlineRate": "Rules not yet readable",
        "annualFee": 0.0,
        "track": "cashback",
        "held": True,
        "deltaVsWallet": 0.0,
        "deltaNote": "Could not read terms.",
        "tags": ["cashback", "no annual fee"],
    }
    assert {"pacePerMonth", "projectedAt"} <= snapshot["goal"].keys()


def test_catalog_marks_existing_entry_as_held_without_duplicating_it():
    store = Store()
    store.set_subdoc("user", "wallet", "card", {
        "cardId": "card", "name": "Known Card", "last4": "1234",
        "network": "Visa", "annualFee": 0, "track": "cashback",
        "rules": [], "parseStatus": "parsed",
    })
    store.set_subdoc("user", "catalog", "known", {
        "name": "Known Card", "network": "Visa", "headlineRate": "2% flat",
        "annualFee": 0, "track": "cashback", "held": False,
        "deltaVsWallet": 12, "tags": ["flat rate"],
    })

    snapshot = Orchestrator(store).empty_snapshot("user")
    assert len(snapshot["catalog"]) == 1
    assert snapshot["catalog"][0]["held"] is True
