from app.orchestrator import Orchestrator
from app.store import Store
from app import main


def test_removing_wallet_card_keeps_global_rules():
    store = Store()
    store.set_global_doc("card_rules", "visa-card", {"rules": [{"categoryLabel": "Dining", "rate": "3%"}]})
    store.set_subdoc("user", "wallet", "visa-card", {"cardId": "visa-card", "name": "Card", "last4": "1234", "network": "Visa", "annualFee": 0, "track": "cashback", "rules": [], "source": {"label": "terms", "locator": "test", "retrievedAt": "2026-01-01"}, "recheckCadence": "weekly", "nextRecheckAt": "2026-01-08", "parseStatus": "parsed"})
    store.delete_subdoc("user", "wallet", "visa-card")
    assert store.get_subdoc("user", "wallet", "visa-card") is None
    assert store.get_global_doc("card_rules", "visa-card") is not None


def test_legacy_wallet_document_uses_its_document_id_as_card_id():
    store = Store()
    store.set_subdoc("user", "wallet", "legacy-card", {"name": "Legacy", "last4": "9876"})
    assert store.get_wallet("user") == [{"id": "legacy-card", "name": "Legacy", "last4": "9876", "walletId": "legacy-card", "cardId": "legacy-card"}]


def test_wallet_id_remains_distinct_from_card_rule_id():
    store = Store()
    store.set_subdoc("user", "wallet", "wallet-random-id", {"cardId": "visa-card", "name": "Card", "last4": "1234"})
    wallet = store.get_wallet("user")
    assert wallet[0]["walletId"] == "wallet-random-id"
    assert wallet[0]["cardId"] == "visa-card"


def test_snapshot_card_gets_authoritative_wallet_id(monkeypatch):
    test_store = Store()
    test_store.set_subdoc(
        "user",
        "wallet",
        "uob-one",
        {"cardId": "uob-one", "name": "UOB One", "last4": "1234"},
    )
    monkeypatch.setattr(main, "store", test_store)

    snapshot = {
        "wallet": [
            {
                "cardId": "added by you-uob-one",
                "name": "UOB One",
                "last4": "1234",
            }
        ]
    }

    normalised = main._normalise_snapshot_wallet(snapshot, "user")
    assert normalised["wallet"][0]["walletId"] == "uob-one"
    assert normalised["wallet"][0]["cardId"] == "added by you-uob-one"
