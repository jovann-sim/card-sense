from datetime import date

import pytest
from fastapi import HTTPException

from app.main import _normalise_plaid_transaction, _plaid_transactions_sync_request
from app.orchestrator import Orchestrator
from app.store import Store


def test_initial_transactions_sync_omits_null_cursor():
    request = _plaid_transactions_sync_request("access-token", None)

    assert request.to_dict() == {"access_token": "access-token"}


def test_subsequent_transactions_sync_includes_cursor():
    request = _plaid_transactions_sync_request("access-token", "next-cursor")

    assert request.to_dict() == {
        "access_token": "access-token",
        "cursor": "next-cursor",
    }


def test_plaid_dates_are_converted_for_firestore_recursively():
    transaction = {
        "transaction_id": "transaction",
        "account_id": "account",
        "date": date(2026, 8, 10),
        "amount": 12.5,
        "name": "Coffee",
        "location": {"observed_on": date(2026, 8, 9)},
        "history": [date(2026, 8, 8)],
    }

    normalized = _normalise_plaid_transaction(transaction)

    assert normalized["date"] == "2026-08-10"
    assert normalized["rawPlaid"]["date"] == "2026-08-10"
    assert normalized["rawPlaid"]["location"]["observed_on"] == "2026-08-09"
    assert normalized["rawPlaid"]["history"] == ["2026-08-08"]


def test_plaid_changes_can_be_applied_as_one_group():
    store = Store()
    store.set_subdoc("user", "transactions", "removed", {"amount": 1})

    store.apply_subdoc_changes(
        "user",
        upserts=[
            ("transactions", "added", {"amount": 2}),
            ("plaid_items", "item", {"cursor": "next"}),
        ],
        deletes=[("transactions", "removed")],
    )

    assert store.get_subdoc("user", "transactions", "added")["amount"] == 2
    assert store.get_subdoc("user", "transactions", "removed") is None
    assert store.get_subdoc("user", "plaid_items", "item")["cursor"] == "next"


# -- ingestion normalisation ------------------------------------------------

def test_plaid_mcc_is_used_when_supplied():
    from app.agents.ingestion import IngestionAgent
    row = IngestionAgent().normalise_plaid({
        "transaction_id": "t1", "amount": 12.0, "merchant_category_code": "5812",
        "personal_finance_category": {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_RESTAURANT"},
    })
    assert row["mcc"] == "5812" and row["mccSource"] == "plaid"


def test_mcc_is_inferred_when_plaid_omits_it():
    """Two thirds of a sandbox pull carry a code; the rest still need matching."""
    from app.agents.ingestion import IngestionAgent
    row = IngestionAgent().normalise_plaid({
        "transaction_id": "t2", "amount": 9.0,
        "personal_finance_category": {"primary": "TRANSPORTATION", "detailed": "TRANSPORTATION_TAXIS_AND_RIDE_SHARES"},
    })
    assert row["mcc"] == "4121" and row["mccSource"] == "inferred"
    assert row["category"] == "Transit"


def test_transfers_and_card_payments_are_not_purchases():
    """Paying your card bill is money moving, not spending that earns rewards."""
    from app.agents.ingestion import IngestionAgent
    agent = IngestionAgent()
    for detailed, primary in [("LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", "LOAN_PAYMENTS"),
                              ("TRANSFER_OUT_ACCOUNT_TRANSFER", "TRANSFER_OUT")]:
        row = agent.normalise_plaid({
            "transaction_id": "t", "amount": 500.0,
            "personal_finance_category": {"primary": primary, "detailed": detailed},
        })
        assert row["isPurchase"] is False, detailed


def test_strategy_ignores_non_purchases():
    from app.agents.strategy import StrategyAgent
    txs = [{"category": "Dining", "amount": 100, "isPurchase": True},
           {"category": "Transfers & payments", "amount": 5000, "isPurchase": False}]
    result = StrategyAgent().run(txs, [], {})
    assert [c["category"] for c in result["categories"]] == ["Dining"]


def test_summary_reports_coverage_gaps():
    from app.agents.ingestion import IngestionAgent
    agent = IngestionAgent()
    summary = agent.summarise([
        {"isPurchase": True, "mcc": "5812", "mccSource": "plaid", "accountId": "a"},
        {"isPurchase": True, "mcc": None, "accountId": None},
        {"isPurchase": False},
    ])
    assert summary["purchases"] == 2 and summary["excluded"] == 1
    assert summary["mccCoverage"] == 0.5
    assert summary["unlinkedToCard"] == 1
    assert agent.degraded(summary), "a coverage gap this large must be surfaced"


# -- account linking --------------------------------------------------------

def test_accounts_auto_link_by_mask(monkeypatch):
    """Plaid's account mask is the last4 the user typed when adding the card."""
    from app import main
    from app.store import Store

    test_store = Store()
    monkeypatch.setattr(main, "store", test_store)
    test_store.set_subdoc("demo-user", "plaid_accounts", "acc-1", {
        "id": "acc-1", "mask": "3333", "type": "credit", "subtype": "credit card"})
    test_store.set_subdoc("demo-user", "wallet", "visa-card", {
        "cardId": "visa-card", "name": "Card", "last4": "3333"})

    linked = main.link_accounts_to_cards("demo-user")
    assert linked and linked[0]["accountId"] == "acc-1"
    assert test_store.get_subdoc("demo-user", "wallet", "visa-card")["accountId"] == "acc-1"


def test_a_depository_account_is_never_linked_to_a_card(monkeypatch):
    """A current account sharing a mask is not the card that earned the reward."""
    from app import main
    from app.store import Store

    test_store = Store()
    monkeypatch.setattr(main, "store", test_store)
    test_store.set_subdoc("demo-user", "plaid_accounts", "acc-2", {
        "id": "acc-2", "mask": "3333", "type": "depository", "subtype": "checking"})
    test_store.set_subdoc("demo-user", "wallet", "visa-card", {
        "cardId": "visa-card", "name": "Card", "last4": "3333"})

    assert main.link_accounts_to_cards("demo-user") == []


def test_an_already_linked_card_is_left_alone(monkeypatch):
    from app import main
    from app.store import Store

    test_store = Store()
    monkeypatch.setattr(main, "store", test_store)
    test_store.set_subdoc("demo-user", "plaid_accounts", "acc-3", {
        "id": "acc-3", "mask": "3333", "type": "credit", "subtype": "credit card"})
    test_store.set_subdoc("demo-user", "wallet", "visa-card", {
        "cardId": "visa-card", "name": "Card", "last4": "3333", "accountId": "chosen-by-hand"})

    assert main.link_accounts_to_cards("demo-user") == []


def test_normal_token_exchange_stores_accounts_and_links_cards(monkeypatch):
    """The browser Link path must do the same account work as sandbox/seed."""
    from app import main
    from app.store import Store

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def to_dict(self):
            return self.payload

    class Client:
        def item_public_token_exchange(self, _request):
            return Response({"item_id": "item-1", "access_token": "access-1"})

        def accounts_get(self, _request):
            return Response({"accounts": [{
                "account_id": "account-1", "mask": "4242", "name": "Credit Card",
                "official_name": "Sandbox Credit", "type": "credit", "subtype": "credit card",
            }]})

    test_store = Store()
    test_store.set_subdoc(main.UID, "wallet", "visa-card", {
        "cardId": "visa-card", "name": "Card", "last4": "4242",
    })
    monkeypatch.setattr(main, "store", test_store)
    monkeypatch.setattr(main, "get_plaid_client", lambda: Client())
    monkeypatch.setattr(main.settings, "plaid_client_id", "client")
    monkeypatch.setattr(main.settings, "plaid_secret", "secret")

    result = main.plaid_exchange(main.ExchangeTokenIn(
        publicToken="public",
        userId=main.UID,
        institutionId="ins-test",
        institutionName="Test Credit Union",
    ))

    assert result["accounts"] == 1
    assert test_store.get_subdoc(main.UID, "plaid_accounts", "account-1")
    assert test_store.get_subdoc(main.UID, "wallet", "visa-card")["accountId"] == "account-1"
    assert main.plaid_items()[0]["institutionName"] == "Test Credit Union"
    assert main.plaid_items()[0]["institutionId"] == "ins-test"


def test_summary_measures_wallet_links_not_presence_of_plaid_account_id():
    from app.agents.ingestion import IngestionAgent

    summary = IngestionAgent().summarise(
        [{"isPurchase": True, "mcc": "5812", "accountId": "plaid-account"}],
        linked_account_ids=set(),
    )

    assert summary["unlinkedToCard"] == 1


def test_pending_transactions_are_not_eligible_spend():
    from app.agents.ingestion import is_eligible_purchase

    assert not is_eligible_purchase({"isPurchase": True, "pending": True})
    assert not is_eligible_purchase({"isPurchase": False, "pending": False})
    assert is_eligible_purchase({"isPurchase": True, "pending": False})


def test_refunds_keep_their_negative_direction():
    from app.agents.ingestion import IngestionAgent

    row = IngestionAgent().normalise_plaid({
        "transaction_id": "refund", "amount": -25,
        "personal_finance_category": {
            "primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_RESTAURANT",
        },
    })

    assert row["amount"] == -25
    assert row["isRefund"] is True


def test_csv_import_is_idempotent_and_keeps_mcc():
    from app.agents.ingestion import IngestionAgent

    store = Store()
    records = [{
        "date": "2026-08-10", "merchant": "Cafe", "amount": "12.50",
        "category": "Dining", "mcc": "5812",
    }]
    agent = IngestionAgent()

    first = agent.import_csv_records("user", store, records, "statement.csv")
    second = agent.import_csv_records("user", store, records, "statement.csv")

    assert first[0]["mcc"] == "5812"
    assert first[0]["id"] == second[0]["id"]
    assert len(store.get_subcollection("user", "transactions")) == 1


def test_scheduler_syncs_plaid_before_running_agents(monkeypatch):
    from app import main
    from app.store import Store

    test_store = Store()
    test_store.set_subdoc(main.UID, "plaid_items", "item", {"accessToken": "token"})
    monkeypatch.setattr(main, "store", test_store)
    monkeypatch.setattr(main.settings, "plaid_client_id", "client")
    monkeypatch.setattr(main.settings, "plaid_secret", "secret")
    monkeypatch.setattr(main.settings, "internal_run_secret", "secret")
    monkeypatch.setattr(main, "plaid_sync", lambda body: {
        "runId": "run", "snapshot": {"generatedAt": "now"},
        "added": 2, "modified": 1, "removed": 0,
    })

    result = main.scheduled_run("secret")

    assert result["runId"] == "run"
    assert result["plaid"] == {"added": 2, "modified": 1, "removed": 0}


def test_disconnect_revokes_item_and_removes_only_its_local_data(monkeypatch):
    from app import main

    removed_tokens = []

    class Client:
        def item_remove(self, request):
            removed_tokens.append(request.to_dict()["access_token"])

    test_store = Store()
    test_orchestrator = Orchestrator(test_store)
    test_store.set_subdoc(main.UID, "plaid_items", "item-a", {"accessToken": "token-a"})
    test_store.set_subdoc(main.UID, "plaid_items", "item-b", {"accessToken": "token-b"})
    test_store.set_subdoc(main.UID, "plaid_accounts", "account-a", {"itemId": "item-a"})
    test_store.set_subdoc(main.UID, "plaid_accounts", "account-b", {"itemId": "item-b"})
    test_store.set_subdoc(main.UID, "transactions", "plaid-a", {
        "source": "plaid", "accountId": "account-a", "amount": 10,
        "date": str(date.today()), "category": "Dining", "isPurchase": True,
    })
    test_store.set_subdoc(main.UID, "transactions", "plaid-b", {
        "source": "plaid", "accountId": "account-b", "amount": 20,
        "date": str(date.today()), "category": "Dining", "isPurchase": True,
    })
    test_store.set_subdoc(main.UID, "transactions", "csv", {
        "source": "csv", "amount": 30, "date": str(date.today()),
        "category": "Dining", "isPurchase": True,
    })
    test_store.set_subdoc(main.UID, "wallet", "card", {
        "cardId": "card", "name": "Card", "last4": "1111", "network": "Visa",
        "track": "cashback", "annualFee": 0, "accountId": "account-a",
        "parseStatus": "parsed",
    })
    test_store.set_subdoc(main.UID, "advice", "old", {"headline": "Stale", "outcome": "open"})
    monkeypatch.setattr(main, "store", test_store)
    monkeypatch.setattr(main, "orch", test_orchestrator)
    monkeypatch.setattr(main, "get_plaid_client", lambda: Client())
    monkeypatch.setattr(main.settings, "plaid_client_id", "client")
    monkeypatch.setattr(main.settings, "plaid_secret", "secret")

    listed = main.plaid_items()
    assert {item["itemId"] for item in listed} == {"item-a", "item-b"}
    assert all("accessToken" not in item for item in listed)

    result = main.disconnect_plaid_item("item-a")

    assert removed_tokens == ["token-a"]
    assert result["plaidRemoved"] is True
    assert result["accountsRemoved"] == 1
    assert result["transactionsRemoved"] == 1
    assert test_store.get_subdoc(main.UID, "plaid_items", "item-a") is None
    assert test_store.get_subdoc(main.UID, "plaid_items", "item-b") is not None
    assert test_store.get_subdoc(main.UID, "transactions", "plaid-a") is None
    assert test_store.get_subdoc(main.UID, "transactions", "plaid-b") is not None
    assert test_store.get_subdoc(main.UID, "transactions", "csv") is not None
    assert test_store.get_subdoc(main.UID, "wallet", "card")["accountId"] is None
    assert test_store.get_subcollection(main.UID, "advice") == []


def test_disconnect_keeps_local_token_when_remote_revocation_fails(monkeypatch):
    from app import main

    class Client:
        def item_remove(self, _request):
            raise RuntimeError("Plaid unavailable")

    test_store = Store()
    test_store.set_subdoc(main.UID, "plaid_items", "item", {"accessToken": "token"})
    monkeypatch.setattr(main, "store", test_store)
    monkeypatch.setattr(main, "get_plaid_client", lambda: Client())
    monkeypatch.setattr(main.settings, "plaid_client_id", "client")
    monkeypatch.setattr(main.settings, "plaid_secret", "secret")

    with pytest.raises(HTTPException):
        main.disconnect_plaid_item("item")

    assert test_store.get_subdoc(main.UID, "plaid_items", "item") is not None


def test_disconnect_requires_credentials_before_deleting_local_token(monkeypatch):
    from app import main

    test_store = Store()
    test_store.set_subdoc(main.UID, "plaid_items", "item", {"accessToken": "token"})
    monkeypatch.setattr(main, "store", test_store)
    monkeypatch.setattr(main.settings, "plaid_client_id", None)
    monkeypatch.setattr(main.settings, "plaid_secret", None)

    with pytest.raises(HTTPException) as unavailable:
        main.disconnect_plaid_item("item")

    assert unavailable.value.status_code == 503
    assert test_store.get_subdoc(main.UID, "plaid_items", "item") is not None


def test_demo_reset_requires_secret_and_preserves_catalog_and_global_rules(monkeypatch):
    from app import main

    test_store = Store()
    test_orchestrator = Orchestrator(test_store)
    test_store.set_subdoc(main.UID, "catalog", "catalog-card", {
        "name": "Catalog Card", "network": "Visa", "headlineRate": "2%",
        "annualFee": 0, "track": "cashback", "held": False,
        "deltaVsWallet": 0, "tags": [],
    })
    test_store.set_global_doc("card_rules", "catalog-card", {"rules": [{"rate": "2%"}]})
    test_store.set_subdoc(main.UID, "wallet", "held", {
        "cardId": "held", "name": "Held", "last4": "1111", "network": "Visa",
        "track": "cashback", "annualFee": 0, "parseStatus": "parsed",
    })
    test_store.set_subdoc(main.UID, "transactions", "spend", {
        "source": "csv", "amount": 100, "date": str(date.today()),
        "category": "Dining", "isPurchase": True,
    })
    test_store.set_user(main.UID, {"goal": {"track": "cashback"}})
    monkeypatch.setattr(main, "store", test_store)
    monkeypatch.setattr(main, "orch", test_orchestrator)
    monkeypatch.setattr(main.settings, "demo_mode", True)
    monkeypatch.setattr(main.settings, "plaid_env", "sandbox")
    monkeypatch.setattr(main.settings, "plaid_client_id", None)
    monkeypatch.setattr(main.settings, "plaid_secret", None)
    monkeypatch.setattr(main.settings, "internal_run_secret", "reset-secret")

    with pytest.raises(HTTPException) as unauthorized:
        main.reset_demo("wrong")
    assert unauthorized.value.status_code == 401

    monkeypatch.setattr(main.settings, "demo_mode", False)
    with pytest.raises(HTTPException) as forbidden:
        main.reset_demo("reset-secret")
    assert forbidden.value.status_code == 403
    monkeypatch.setattr(main.settings, "demo_mode", True)

    result = main.reset_demo("reset-secret")

    assert result["snapshot"]["totals"] == {
        "spend": 0.0,
        "refunds": 0.0,
        "netSpend": 0.0,
        "captured": 0.0,
        "unclaimed": 0.0,
    }
    assert result["snapshot"]["wallet"] == []
    assert test_store.get_subcollection(main.UID, "transactions") == []
    assert test_store.get_user(main.UID).get("goal") is None
    assert len(test_store.get_subcollection(main.UID, "catalog")) == 1
    assert test_store.get_global_doc("card_rules", "catalog-card") is not None
