from datetime import date, timedelta

from fastapi import BackgroundTasks

from app.orchestrator import Orchestrator
from app.store import Store
from app.models import AdviceResolveIn, GoalIn, PlannedItemIn, RunIn, Snapshot
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


def test_empty_snapshot_reports_agents_as_not_run_without_fake_timestamps():
    snapshot = Orchestrator(Store()).empty_snapshot("test-user")

    assert snapshot["activity"] == []
    assert {agent["status"] for agent in snapshot["agents"]} == {"not-run"}
    assert all(agent["lastRunAt"] is None for agent in snapshot["agents"])


def test_async_run_is_visible_while_queued_and_completes_with_real_agent_records(monkeypatch):
    store = Store()
    orchestrator = Orchestrator(store)
    background = BackgroundTasks()
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "orch", orchestrator)

    started = main.start_agent_run(RunIn(request="Onboarding"), background)
    queued = main.run_status(started["runId"])

    assert started["status"] == "queued"
    assert queued["status"] == "queued"
    assert [agent["status"] for agent in queued["agents"]] == ["queued"] * 5

    main._execute_background_run(orchestrator, started["runId"], "Onboarding")
    complete = main.run_status(started["runId"])

    assert complete["status"] == "complete"
    assert [agent["id"] for agent in complete["agents"]] == [
        "ingestion", "card-intelligence", "strategy", "forecast", "advisory",
    ]
    assert {agent["status"] for agent in complete["agents"]} <= {"ok", "degraded"}
    assert store.get_user(main.UID)["lastRunId"] == started["runId"]


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

    planned_date = date.today() + timedelta(days=10)
    snapshot = main.add_planned(PlannedItemIn(
        kind="purchase",
        label="Laptop",
        startDate=planned_date,
        amount=2000,
        categories=["Online retail"],
    ))

    assert snapshot["planned"][0]["label"] == "Laptop"
    assert snapshot["forecast"]["timeline"][0]["title"] == "Laptop"
    assert snapshot["forecast"]["plannedSpend"] == 2000
    assert snapshot["forecast"]["projectedSpend"] == 2000

    removed = main.delete_planned(snapshot["planned"][0]["id"])
    assert removed["planned"] == []
    assert removed["forecast"]["timeline"] == []
    assert removed["forecast"]["plannedSpend"] == 0
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

    cleared = main.clear_goal()
    assert cleared["goal"] is None
    assert cleared["trackPreference"] is None
    assert cleared["recommendedTrack"] == "cashback"


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


def test_agent_run_replaces_stale_open_advice_by_run_id():
    store = Store()
    orchestrator = Orchestrator(store)
    store.set_subdoc("user", "advice", "keep", {
        "id": "keep", "runId": "old-run", "outcome": "open",
        "headline": "Keep this advice", "impact": 4, "predicted": 4,
        "pushedAt": "2026-08-01T00:00:00+00:00", "window": "per period",
    })
    store.set_subdoc("user", "advice", "stale", {
        "id": "stale", "runId": "old-run", "outcome": "open",
        "headline": "No longer supported", "impact": 7, "predicted": 7,
        "pushedAt": "2026-08-01T00:00:00+00:00", "window": "per period",
    })
    store.set_subdoc("user", "advice", "dismissed", {
        "id": "dismissed", "runId": "old-run", "outcome": "dismissed",
        "headline": "Already dismissed", "impact": 3, "predicted": 3,
        "pushedAt": "2026-08-01T00:00:00+00:00", "window": "per period",
    })
    orchestrator.advisory.run = lambda *_args: [
        {
            "id": "keep", "urgency": "this-week",
            "headline": "Keep this advice", "card": None, "impact": 5,
            "impactWindow": "per period", "body": "Still current.", "trace": [],
        },
        {
            "id": "new", "urgency": "this-week",
            "headline": "New advice", "card": None, "impact": 2,
            "impactWindow": "per period", "body": "New finding.", "trace": [],
        },
        {
            "id": "dismissed", "urgency": "this-week",
            # Wording may change between Gemini calls. The stable semantic ID,
            # not an exact headline match, preserves the user's resolution.
            "headline": "Reworded but already dismissed", "card": None, "impact": 3,
            "impactWindow": "per period", "body": "Do not reopen.", "trace": [],
        },
    ]

    run_id, snapshot = orchestrator.run("user")

    assert {item["id"] for item in snapshot["recommendations"]} == {"keep", "new"}
    assert store.get_subdoc("user", "advice", "keep")["runId"] == run_id
    assert store.get_subdoc("user", "advice", "new")["runId"] == run_id
    stale = store.get_subdoc("user", "advice", "stale")
    assert stale["outcome"] == "expired"
    assert stale["invalidatedByRunId"] == run_id
    dismissed = store.get_subdoc("user", "advice", "dismissed")
    assert dismissed["outcome"] == "dismissed"
    assert dismissed["runId"] == "old-run"
    # Superseding stale advice is not counted as a user missing valid advice.
    assert snapshot["trackRecord"]["missed"] == 3


def test_skipped_advisory_expires_open_advice_instead_of_retaining_it():
    store = Store()
    orchestrator = Orchestrator(store)
    store.set_subdoc("user", "advice", "old", {
        "id": "old", "outcome": "open", "headline": "Old advice",
        "impact": 4, "predicted": 4, "window": "per period",
    })

    run_id, snapshot = orchestrator.run("user", refresh_advice=False)

    old = store.get_subdoc("user", "advice", "old")
    assert old["outcome"] == "expired"
    assert old["invalidatedByRunId"] == run_id
    assert snapshot["recommendations"] == []
    advisory = next(agent for agent in snapshot["agents"] if agent["id"] == "advisory")
    assert advisory["status"] == "degraded"


def test_projection_never_surfaces_open_advice_from_another_run():
    store = Store()
    orchestrator = Orchestrator(store)
    store.set_subdoc("user", "advice", "legacy-open", {
        "id": "legacy-open", "runId": "older-run", "outcome": "open",
        "headline": "Stale advice", "urgency": "this-week", "card": None,
        "impact": 9, "impactWindow": "per period", "body": "Old.", "trace": [],
    })

    snapshot = orchestrator.project("user", "current-run")

    assert snapshot["recommendations"] == []
    assert snapshot["trackRecord"]["records"][0]["runId"] == "older-run"


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
    card_agent = next(agent for agent in snapshot["agents"] if agent["id"] == "card-intelligence")
    assert card_agent["status"] == "degraded"
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


def test_non_purchases_and_pending_rows_do_not_inflate_snapshot_or_forecast():
    store = Store()
    today = date.today()
    for ident, transaction in {
        "purchase": {"amount": 100, "date": str(today - timedelta(days=9)), "category": "Dining", "isPurchase": True},
        "refund": {"amount": -20, "date": str(today - timedelta(days=8)), "category": "Dining", "isPurchase": True},
        "pending": {"amount": 30, "date": str(today - timedelta(days=7)), "category": "Dining", "isPurchase": True, "pending": True},
        "transfer": {"amount": 500, "date": str(today - timedelta(days=6)), "category": "Transfers", "isPurchase": False},
    }.items():
        store.set_subdoc("user", "transactions", ident, transaction)

    _, snapshot = Orchestrator(store).run("user")

    assert snapshot["totals"]["spend"] == 100
    assert snapshot["totals"]["refunds"] == 20
    assert snapshot["totals"]["netSpend"] == 80
    # Ten calendar days from the first eligible row through today:
    # net spend 80 / 10 observed days * the 30-day horizon.
    assert snapshot["forecast"]["baselineSpend"] == 240
    assert snapshot["forecast"]["projectedSpend"] == 240


def test_forecast_cost_uses_observed_strategy_leakage_rate():
    store = Store()
    for card_id, name, account_id in (
        ("used", "Used Card", "acct-used"),
        ("best", "Best Card", None),
    ):
        store.set_subdoc("user", "wallet", card_id, {
            "cardId": card_id,
            "name": name,
            "last4": "1111" if card_id == "used" else "2222",
            "network": "Visa",
            "track": "cashback",
            "annualFee": 0,
            "accountId": account_id,
            "parseStatus": "parsed",
        })
    store.set_global_doc("card_rules", "used", {"rules": [{
        "categoryLabel": "Dining", "valuePerDollar": 0.01, "rate": "1%",
        "capSpend": None, "cycleLabel": "no cap",
    }]})
    store.set_global_doc("card_rules", "best", {"rules": [{
        "categoryLabel": "Dining", "valuePerDollar": 0.05, "rate": "5%",
        "capSpend": None, "cycleLabel": "no cap",
    }]})
    store.set_subdoc("user", "transactions", "meal", {
        "date": str(date.today()), "amount": 100, "category": "Dining",
        "accountId": "acct-used", "isPurchase": True,
    })

    _, snapshot = Orchestrator(store).run("user")

    assert snapshot["totals"]["unclaimed"] == 4
    assert snapshot["forecast"]["projectedSpend"] == 3000
    assert snapshot["forecast"]["doNothingCost"] == 120
