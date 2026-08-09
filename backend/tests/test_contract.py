from app.orchestrator import Orchestrator
from app.store import Store
from app.models import Snapshot


def test_snapshot_is_persisted_as_a_subcollection_read_model():
    store = Store()
    orchestrator = Orchestrator(store)
    run_id, snapshot = orchestrator.run("test-user")
    assert Snapshot.model_validate(snapshot)
    assert store.get_snapshot("test-user")["generatedAt"] == snapshot["generatedAt"]
    assert store.get_subdoc("test-user", "forecasts", run_id)
    assert store.get_subdoc("test-user", "strategy_runs", run_id)
    assert len(store.get_subcollection("test-user", "agent_runs")) == 5


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
