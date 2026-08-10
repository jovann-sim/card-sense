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
