from datetime import date

from app.main import _normalise_plaid_transaction, _plaid_transactions_sync_request
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
