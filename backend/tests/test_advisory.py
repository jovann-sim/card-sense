from app.agents.advisory import AdvisoryAgent, AdvisoryWording, AdvisoryWordingOutput


WALLET = [{
    "cardId": "dining-card",
    "name": "Dining Card",
    "last4": "1234",
    "parseStatus": "parsed",
    "rules": [],
}]


def category(**overrides):
    return {
        "category": "Dining",
        "bestCard": "Dining Card",
        "unclaimed": 8.25,
        "flags": [],
        **overrides,
    }


class WordingRuntime:
    def __init__(self, output=None, error=None):
        self.output = output or AdvisoryWordingOutput()
        self.error = error

    def structured(self, _prompt, schema):
        assert schema is AdvisoryWordingOutput
        if self.error:
            raise self.error
        return self.output


def test_financial_facts_and_card_identity_are_deterministic():
    invented = AdvisoryWordingOutput(recommendations=[AdvisoryWording(
        category="Dining",
        headline="Use Imaginary Card for Dining and earn $999",
        body="Imaginary Card returns 99% on Dining.",
    )])

    result = AdvisoryAgent(WordingRuntime(invented)).run(
        {"categories": [category()]}, {}, WALLET,
    )

    assert len(result) == 1
    assert result[0]["id"] == "rec-route-dining-dining-card"
    assert result[0]["card"] == {"name": "Dining Card", "last4": "1234"}
    assert result[0]["impact"] == 8.25
    assert "Imaginary" not in result[0]["headline"]
    assert "$999" not in result[0]["body"]


def test_safe_model_wording_can_change_language_only():
    wording = AdvisoryWordingOutput(recommendations=[AdvisoryWording(
        category="Dining",
        headline="Reach for Dining Card when you dine",
        body="Dining Card is the verified choice for Dining while its applicable terms allow.",
    )])

    result = AdvisoryAgent(WordingRuntime(wording)).run(
        {"categories": [category()]}, {}, WALLET,
    )

    assert result[0]["headline"] == "Reach for Dining Card when you dine"
    assert result[0]["body"].startswith("Dining Card is the verified choice")
    assert result[0]["impact"] == 8.25
    assert result[0]["trace"][0]["agent"] == "strategy"


def test_small_or_zero_findings_do_not_become_recommendations():
    result = AdvisoryAgent(WordingRuntime()).run(
        {"categories": [category(unclaimed=0), category(category="Fuel", unclaimed=0.99)]},
        {},
        WALLET,
    )
    assert result == []


def test_unknown_best_card_is_rejected():
    result = AdvisoryAgent(WordingRuntime()).run(
        {"categories": [category(bestCard="Invented Card")]}, {}, WALLET,
    )
    assert result == []


def test_model_failure_uses_deterministic_fallback():
    result = AdvisoryAgent(WordingRuntime(error=RuntimeError("offline"))).run(
        {"categories": [category()]}, {}, WALLET,
    )
    assert result[0]["headline"] == "Use Dining Card for Dining"
    assert result[0]["card"]["last4"] == "1234"


def test_setup_actions_use_real_cards_and_do_not_claim_an_unknown_impact():
    wallet = [{
        **WALLET[0],
        "rules": [{
            "categoryLabel": "Dining",
            "conditions": [{
                "kind": "enrolment",
                "description": "Activate the category first.",
            }],
        }],
    }]
    result = AdvisoryAgent(WordingRuntime()).run(
        {"categories": [category(unclaimed=0, flags=["conditional-rate"], note="Activate first.")]},
        {},
        wallet,
    )

    assert len(result) == 1
    assert result[0]["card"] == {"name": "Dining Card", "last4": "1234"}
    assert result[0]["impact"] == 0
    assert result[0]["impactWindow"] == "unknown until verified"
    assert "0000" not in str(result[0])


def test_plan_actions_use_the_held_cards_real_identifier():
    simulation = {
        "steps": [{
            "kind": "reassign",
            "rank": 1,
            "value": 76.97,
            "valueWindow": "over the period priced",
            "card": "Dining Card",
            "title": "Move dining to Dining Card",
            "detail": "Dining Card earns more on this spending.",
        }],
    }

    result = AdvisoryAgent(WordingRuntime()).run(
        {"categories": []}, {}, WALLET, simulation=simulation,
    )

    assert len(result) == 1
    assert result[0]["card"] == {"name": "Dining Card", "last4": "1234"}
    assert "0000" not in str(result[0])


def test_plan_actions_do_not_invent_an_identifier_for_an_unheld_card():
    simulation = {
        "steps": [{
            "kind": "acquire",
            "rank": 1,
            "value": 100.0,
            "valueWindow": "per year, net of fee",
            "title": "Consider a new card",
            "detail": "This unheld card would improve annual rewards.",
        }],
    }

    result = AdvisoryAgent(WordingRuntime()).run(
        {"categories": []}, {}, WALLET, simulation=simulation,
    )

    assert len(result) == 1
    assert result[0]["card"] is None
    assert "0000" not in str(result[0])


def welcome_progress(card="Dining Card"):
    return {
        "card": card,
        "state": "at-risk",
        "qualifyingSpend": 3_000.0,
        "minSpend": 4_000.0,
        "gap": 1_000.0,
        "daysLeft": 10,
        "perDayNeeded": 100.0,
        "perDayCurrent": 50.0,
        "valueUsd": 600.0,
        "deadline": "2026-08-26",
        "award": 60_000,
        "unit": "points",
        "transactions": 12,
        "openedAt": "2026-05-28",
        "rescue": None,
    }


def test_welcome_actions_use_the_held_cards_real_identifier():
    result = AdvisoryAgent(WordingRuntime()).run(
        {"categories": []}, {}, WALLET, welcome=[welcome_progress()],
    )

    assert len(result) == 1
    assert result[0]["card"] == {"name": "Dining Card", "last4": "1234"}
    assert "0000" not in str(result[0])


def test_welcome_actions_do_not_invent_an_identifier_for_an_unknown_card():
    result = AdvisoryAgent(WordingRuntime()).run(
        {"categories": []}, {}, WALLET,
        welcome=[welcome_progress(card="Unknown Card")],
    )

    assert len(result) == 1
    assert result[0]["card"] is None
    assert "0000" not in str(result[0])
