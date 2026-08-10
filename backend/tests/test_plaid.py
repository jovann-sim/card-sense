from app.main import _plaid_transactions_sync_request


def test_initial_transactions_sync_omits_null_cursor():
    request = _plaid_transactions_sync_request("access-token", None)

    assert request.to_dict() == {"access_token": "access-token"}


def test_subsequent_transactions_sync_includes_cursor():
    request = _plaid_transactions_sync_request("access-token", "next-cursor")

    assert request.to_dict() == {
        "access_token": "access-token",
        "cursor": "next-cursor",
    }
