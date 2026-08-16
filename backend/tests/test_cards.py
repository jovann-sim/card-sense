import pytest
from pydantic import ValidationError

from app.orchestrator import Orchestrator
from app.store import Store
from app import main
from app.models import CardIn, CardMetadataIn


def test_card_input_preserves_opening_date_and_requires_four_digits():
    card = CardIn(
        name="Card", last4="1234", network="Visa", track="cashback",
        openedAt="2026-08-01",
    )

    assert card.model_dump(mode="json")["openedAt"] == "2026-08-01"

    for invalid in ("", "123", "12345", "12a4"):
        with pytest.raises(ValidationError):
            CardIn(name="Card", last4=invalid, network="Visa", track="cashback")


def test_adding_a_card_persists_its_opening_date(monkeypatch):
    test_store = Store()
    orchestrator = Orchestrator(test_store)
    monkeypatch.setattr(main, "store", test_store)
    monkeypatch.setattr(main, "orch", orchestrator)

    response = main.add_card(CardIn(
        name="New Card", last4="1234", network="Visa", track="cashback",
        openedAt="2026-08-01",
        rules=[{"categoryLabel": "Dining", "rate": "3%"}],
    ))

    assert response["card"]["openedAt"] == "2026-08-01"
    assert response["snapshot"]["wallet"][0]["openedAt"] == "2026-08-01"


def test_editing_card_metadata_preserves_rules_provenance_and_linkage(monkeypatch):
    test_store = Store()
    rules = [{"id": "dining", "categoryLabel": "Dining", "rate": "3%"}]
    source = {
        "label": "Issuer terms", "locator": "https://example.test/terms",
        "retrievedAt": "2026-08-01",
    }
    test_store.set_global_doc("card_rules", "card", {
        "rules": rules, "source": source, "status": "parsed", "confidence": 1,
    })
    test_store.set_subdoc(main.UID, "wallet", "card", {
        "cardId": "card", "name": "Card", "last4": "1111", "network": "Visa",
        "annualFee": 0, "track": "cashback", "openedAt": None,
        "accountId": "plaid-account", "accountAutoLinkDisabled": False,
        "rules": rules, "source": source, "parseStatus": "parsed",
        "parseConfidence": 1, "recheckCadence": "weekly",
        "nextRecheckAt": "2026-08-22", "termsUrl": source["locator"],
    })
    orchestrator = Orchestrator(test_store)
    monkeypatch.setattr(main, "store", test_store)
    monkeypatch.setattr(main, "orch", orchestrator)

    response = main.update_card_metadata(
        "card", CardMetadataIn(last4="9999", openedAt="2026-07-15"),
    )
    stored = test_store.get_subdoc(main.UID, "wallet", "card")

    assert response["card"]["last4"] == "9999"
    assert response["snapshot"]["wallet"][0]["openedAt"] == "2026-07-15"
    assert stored["rules"] == rules
    assert stored["source"] == source
    assert stored["accountId"] == "plaid-account"
    assert stored["termsUrl"] == source["locator"]
    assert test_store.get_global_doc("card_rules", "card")["rules"] == rules


def test_removing_wallet_card_keeps_global_rules():
    store = Store()
    store.set_global_doc("card_rules", "visa-card", {"rules": [{"categoryLabel": "Dining", "rate": "3%"}]})
    store.set_subdoc("user", "wallet", "visa-card", {"cardId": "visa-card", "name": "Card", "last4": "1234", "network": "Visa", "annualFee": 0, "track": "cashback", "rules": [], "source": {"label": "terms", "locator": "test", "retrievedAt": "2026-01-01"}, "recheckCadence": "weekly", "nextRecheckAt": "2026-01-08", "parseStatus": "parsed"})
    store.delete_subdoc("user", "wallet", "visa-card")
    assert store.get_subdoc("user", "wallet", "visa-card") is None
    assert store.get_global_doc("card_rules", "visa-card") is not None


def test_card_delete_skips_advisory_model_call(monkeypatch):
    store = Store()
    store.set_global_doc("card_rules", "visa-card", {"rules": []})
    store.set_subdoc(main.UID, "wallet", "visa-card", {
        "cardId": "visa-card", "name": "Card", "last4": "1234",
        "network": "Visa", "annualFee": 0, "track": "cashback",
        "rules": [], "parseStatus": "parsed",
    })
    orchestrator = Orchestrator(store)

    def unexpected_advisory(*_args, **_kwargs):
        raise AssertionError("card deletion must not invoke Advisory")

    orchestrator.advisory.run = unexpected_advisory
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "orch", orchestrator)

    snapshot = main.delete_card("visa-card")

    assert snapshot["wallet"] == []
    assert store.get_subdoc(main.UID, "wallet", "visa-card") is None
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


def test_snapshot_migration_only_reads_wallet_once(monkeypatch):
    class CountingStore(Store):
        wallet_reads = 0

        def get_wallet(self, uid):
            self.wallet_reads += 1
            return super().get_wallet(uid)

    test_store = CountingStore()
    old_snapshot = Orchestrator(test_store).empty_snapshot(main.UID)
    old_snapshot.pop("readModelVersion")
    test_store.set_snapshot(main.UID, old_snapshot)
    test_store.wallet_reads = 0
    monkeypatch.setattr(main, "store", test_store)

    first = main.snapshot()
    second = main.snapshot()

    assert first["readModelVersion"] == main.READ_MODEL_VERSION
    assert second["readModelVersion"] == main.READ_MODEL_VERSION
    assert test_store.wallet_reads == 1
    assert {agent["status"] for agent in first["agents"]} == {"not-run"}
    assert all(agent["lastRunAt"] is None for agent in first["agents"])
