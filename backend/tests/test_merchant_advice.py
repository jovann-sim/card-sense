import pytest
from datetime import date

from app.agents.advisory import AdvisoryAgent
from app.merchants import DOMAIN_MCC, domain_key, hostname, resolve

WALLET = [
    {"cardId": "blue", "name": "Blue Cash", "last4": "1111", "track": "cashback", "parseStatus": "parsed"},
    {"cardId": "jrny", "name": "Journey", "last4": "2222", "track": "miles", "parseStatus": "parsed"},
]
RULES = {
    "blue": [
        {"id": "g", "categoryLabel": "U.S. Supermarkets", "rate": "6% cash back", "valuePerDollar": 0.06,
         "mccCodes": ["5411", "5422", "5451", "5499"], "capSpend": 6000, "cycleLabel": "per year"},
        {"id": "b", "categoryLabel": "Everything else", "rate": "1% cash back", "valuePerDollar": 0.01, "mccCodes": []},
    ],
    "jrny": [
        {"id": "d", "categoryLabel": "Dining", "rate": "3 mpd", "valuePerDollar": 0.039,
         "mccCodes": ["5811", "5812", "5813", "5814"]},
        {"id": "b2", "categoryLabel": "Everything else", "rate": "1.2 mpd", "valuePerDollar": 0.0156, "mccCodes": []},
    ],
}


def advise(url, merchant=None, wallet=None, rules=None, transactions=None):
    return AdvisoryAgent(None).verdict(
        resolve(url, merchant), wallet or WALLET, rules or RULES,
        transactions=transactions or [],
    )


# -- reading a location -----------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("https://www.doordash.com/checkout", "doordash.com"),
    ("doordash.com", "doordash.com"),
    ("http://shop.example.co.uk/a/b", "shop.example.co.uk"),
])
def test_a_host_is_read_from_whatever_form_it_arrives_in(value, expected):
    assert hostname(value) == expected


def test_a_regional_domain_keys_on_the_same_merchant():
    """amazon.co.uk and smile.amazon.com are one merchant, not three."""
    assert domain_key("www.amazon.co.uk") == domain_key("smile.amazon.com") == "amazon"


def test_a_known_merchant_resolves_with_confidence():
    result = resolve("https://www.instacart.com/store")
    assert result["mcc"] == "5411" and result["confidence"] == "high"


def test_an_unknown_merchant_says_so_rather_than_guessing():
    """A confident wrong card at checkout is worse than no popup."""
    result = resolve("https://some-shop-nobody-knows.xyz/pay")
    assert result["mcc"] is None and result["confidence"] == "none"


def test_a_category_word_in_the_name_is_a_hint_not_a_fact():
    result = resolve("https://belmont-hotel.example", "Belmont Hotel")
    assert result["mcc"] == "7011" and result["confidence"] == "low"


def test_every_domain_in_the_table_carries_a_usable_code():
    for key, (mcc, category) in DOMAIN_MCC.items():
        assert mcc.isdigit() and len(mcc) == 4, key
        assert category


# -- picking a card ---------------------------------------------------------

def test_the_best_card_for_the_merchant_wins():
    assert advise("https://www.instacart.com")["card"]["name"] == "Blue Cash"
    assert advise("https://www.doordash.com")["card"]["name"] == "Journey"


def test_a_cap_is_stated_because_the_rate_stops_at_it():
    verdict = advise("https://www.instacart.com")
    assert verdict["cap"]["limit"] == 6000
    assert verdict["cap"]["status"] == "unverified"


def test_remaining_cap_is_calculated_from_linked_transactions():
    wallet = [{**WALLET[0], "accountId": "account-blue"}]
    transactions = [{
        "id": "grocery", "accountId": "account-blue", "amount": 1250,
        "date": date.today().isoformat(), "category": "Groceries", "mcc": "5411",
        "isPurchase": True,
    }]
    verdict = AdvisoryAgent(None).verdict(
        resolve("https://www.instacart.com"), wallet, RULES,
        transactions=transactions,
    )
    assert verdict["cap"] == {
        "status": "verified", "limit": 6000.0, "used": 1250.0,
        "remaining": 4750.0, "cycleLabel": "per year",
    }


def test_verdict_exposes_combined_recommendation_confidence():
    verdict = advise("https://belmont-hotel.example", merchant="Belmont Hotel")
    assert verdict["recommendationConfidence"] == "low"


def test_the_runner_up_is_offered_so_the_choice_is_visible():
    verdict = advise("https://www.doordash.com")
    assert "Blue Cash" in verdict["runnerUp"]


def test_an_unknown_merchant_produces_no_card():
    verdict = advise("https://some-shop-nobody-knows.xyz")
    assert verdict["card"] is None and verdict["known"] is False


def test_a_wallet_with_no_matching_rule_declines():
    """Better to say nothing than to name a card that does not cover this."""
    bare = [{"cardId": "x", "name": "Mystery", "last4": "9999", "track": "cashback", "parseStatus": "parsed"}]
    verdict = advise("https://www.doordash.com", wallet=bare, rules={"x": []})
    assert verdict["card"] is None and verdict["known"] is True


def test_an_unreadable_card_is_never_recommended():
    unread = [{**WALLET[0], "parseStatus": "failed"}]
    verdict = advise("https://www.instacart.com", wallet=unread, rules=RULES)
    assert verdict["card"] is None


def test_a_tie_is_presented_as_a_tie():
    tied_rules = {
        "blue": [{"id": "a", "categoryLabel": "Dining", "rate": "3%", "valuePerDollar": 0.03, "mccCodes": ["5814"]}],
        "jrny": [{"id": "b", "categoryLabel": "Dining", "rate": "3%", "valuePerDollar": 0.03, "mccCodes": ["5814"]}],
    }
    verdict = advise("https://www.doordash.com", rules=tied_rules)
    assert verdict["tied"] is True
    assert "either is fine" in verdict["reason"]


def test_every_verdict_explains_itself():
    verdict = advise("https://www.doordash.com")
    agents = {step["agent"] for step in verdict["trace"]}
    assert {"ingestion", "card-intelligence", "strategy"} <= agents


def test_the_verdict_never_contains_a_card_number():
    """The extension is advisory only; last4 is an identifier, not a number."""
    verdict = advise("https://www.instacart.com")
    assert len(verdict["card"]["last4"]) == 4
    assert "pan" not in verdict and "cardNumber" not in verdict


# -- what a public deployment may be asked to do ----------------------------

def test_seeding_endpoints_refuse_an_unauthorised_caller():
    """The service is deployed unauthenticated so the extension can reach it.

    That is fine for reading and not fine for an endpoint that wipes every
    transaction: anyone who found the URL could empty the demo halfway through
    it being judged.
    """
    import fastapi
    from app import main

    for call in (
        lambda: main.seed_realistic_demo(months=12, x_internal_secret="wrong"),
        lambda: main.seed_catalog(x_internal_secret=None),
        lambda: main.plaid_sandbox_seed(main.LinkTokenIn(), x_internal_secret="wrong"),
    ):
        with pytest.raises(fastapi.HTTPException) as raised:
            call()
        assert raised.value.status_code == 401


def test_real_mode_refuses_to_boot_on_the_placeholder_secret():
    """Shipping the default would leave the gate open to anyone who read the repo."""
    from app.config import Settings

    errors = Settings(demo_mode=False, google_cloud_project="p",
                      internal_run_secret="change-me").real_mode_errors()
    assert any("INTERNAL_RUN_SECRET" in error for error in errors)

    assert Settings(demo_mode=False, google_cloud_project="p",
                    internal_run_secret="a-real-one").real_mode_errors() == []


def test_demo_mode_still_boots_without_ceremony():
    """A laptop with no credentials must stay one command away from running."""
    from app.config import Settings

    assert Settings(demo_mode=True).real_mode_errors() == []
