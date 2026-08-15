from datetime import date

from app.agents.forecast import ForecastAgent
from app.agents.recurring import commitments, detect_streams
from app.demo_data import generate, summarise

TODAY = date(2026, 8, 11)


def rows():
    return generate(today=TODAY, months=12, account_ids=["acct-a"])


def test_the_dataset_is_reproducible():
    """A demo that shows different numbers each run cannot be rehearsed."""
    assert [r["id"] for r in rows()] == [r["id"] for r in rows()]


def test_every_row_carries_what_the_pipeline_needs():
    for row in rows():
        assert row["date"] and row["merchant"] and row["id"]
        assert isinstance(row["amount"], float)
        assert "isPurchase" in row and "category" in row


def test_ids_are_unique_so_a_reseed_replaces_rather_than_duplicates():
    generated = rows()
    assert len(generated) == len({row["id"] for row in generated})


def test_it_covers_a_year_and_excludes_income_from_spend():
    summary = summarise(rows())
    assert summary["excluded"] == 12          # twelve monthly salary credits
    assert summary["purchases"] > 500
    assert summary["spend"] > 40_000


def test_the_commitments_are_the_ones_a_person_would_name():
    """The point of the dataset: bills that look like bills.

    On the Plaid sandbox this same detector calls an airline and a fried
    chicken shop monthly subscriptions, because the sandbox charges both
    exactly $500 every thirty days.
    """
    bills = commitments(detect_streams(rows(), today=TODAY))
    named = {stream["merchant"] for stream in bills}

    assert "Greystone Property Mgmt" in named    # rent
    assert "Netflix" in named and "Spotify" in named
    assert "Con Edison" in named                 # varies with the season
    assert not named & {"United Airlines", "Whole Foods Market", "Starbucks", "Amazon"}


def test_no_variable_merchant_is_mistaken_for_a_commitment():
    streams = detect_streams(rows(), today=TODAY)
    habits = [s["merchant"] for s in streams if s["kind"] == "habit"]

    assert "Greystone Property Mgmt" not in habits


def test_the_projection_looks_like_a_household_budget():
    forecast = ForecastAgent().run(rows(), [], today=TODAY, horizon_months=1)

    assert 3_000 < forecast["projectedSpend"] < 8_000
    assert forecast["recurringSpend"] > 2_000     # rent dominates, as it should
    assert forecast["variableSpend"] > 1_000      # and is not the whole story
    # A month out, a household's spend is uncertain but not unknowable.
    assert 0.05 < forecast["confidence"] / forecast["projectedSpend"] < 0.45


def test_the_range_stays_sane_across_every_offered_horizon():
    agent = ForecastAgent()
    for months in (1, 3, 6, 12):
        forecast = agent.run(rows(), [], today=TODAY, horizon_months=months)
        ratio = forecast["confidence"] / forecast["projectedSpend"]
        assert 0.05 < ratio < 0.5, f"{months}mo band was {ratio:.0%} of the figure"


# -- advisory robustness ----------------------------------------------------

def test_a_failing_model_does_not_take_down_the_run():
    """Deterministic figures must survive the wording step failing.

    The model supplies language only; every number is attached afterwards. So a
    model that errors should cost the phrasing, never the advice.
    """
    from app.agents.advisory import AdvisoryAgent
    from app.agents.strategy import StrategyAgent

    class Runtime:
        available = True
        def structured(self, *args, **kwargs):
            raise RuntimeError("model unavailable")

    wallet, rules = _wallet_and_rules()
    strategy = StrategyAgent().run([_tx("Dining", "5812", 900.0, "d")], wallet, rules)
    advice = AdvisoryAgent(Runtime()).run(strategy, {}, wallet)

    assert isinstance(advice, list)
    assert all(isinstance(item.get("impact"), float) for item in advice)


# -- spending no card can reach ---------------------------------------------

def _wallet_and_rules():
    wallet = [{"cardId": "c", "name": "Blue Cash", "last4": "1111", "network": "Visa",
               "track": "cashback", "accountId": "a", "parseStatus": "parsed"}]
    rules = {"c": [{"id": "base", "categoryLabel": "Everything else", "rate": "2%", "valuePerDollar": 0.02}]}
    return wallet, rules


def _tx(category, mcc, amount, tid="t"):
    return {"id": tid, "date": "2026-08-01", "merchant": "M", "amount": amount,
            "category": category, "mcc": mcc, "isPurchase": True, "accountId": "a"}


def test_rent_is_never_priced_as_card_spend():
    """A landlord does not take a Visa, so a rate on rent is a fiction.

    On a real account rent is the largest line, which made it the largest
    fiction: it was reporting captured reward and an unclaimed gap on money no
    card could ever have touched.
    """
    from app.agents.strategy import StrategyAgent

    wallet, rules = _wallet_and_rules()
    result = StrategyAgent().run(
        [_tx("Rent", "6513", 2150.0, "r"), _tx("Dining", "5812", 40.0, "d")], wallet, rules
    )

    assert [c["category"] for c in result["categories"]] == ["Dining"]
    assert [r["category"] for r in result["routable"]] == ["Rent"]


def test_routing_rent_for_the_reward_alone_is_reported_as_a_loss():
    from app.agents.strategy import StrategyAgent

    wallet, rules = _wallet_and_rules()
    routed = StrategyAgent().run([_tx("Rent", "6513", 2150.0, "r")], wallet, rules)["routable"][0]

    assert routed["fee"] > routed["reward"]
    assert routed["net"] < 0
    assert routed["worthIt"] is False
    assert "welcome-bonus" in routed["verdict"]


def test_every_modelled_service_is_offered_for_comparison():
    from app.agents.strategy import StrategyAgent
    from app.routing import SERVICES

    wallet, rules = _wallet_and_rules()
    for choice in (None, "cardup", "melio"):
        routed = StrategyAgent().run([_tx("Rent", "6513", 2150.0, "r")], wallet, rules,
                                     routing=choice)["routable"][0]
        assert len(routed["alternatives"]) == len(SERVICES)
        if choice:
            assert routed["service"] == choice


def test_a_cheaper_service_loses_less():
    from app.routing import price

    dear = price(2150.0, 0.02, 0.029)
    cheap = price(2150.0, 0.02, 0.026)
    assert cheap["net"] > dear["net"]
    assert cheap["net"] < 0            # cheaper, still a losing trade


def test_reaching_a_welcome_bonus_is_the_case_that_wins():
    from app.routing import bonus_case

    assert bonus_case(0, 600, 0.029) is None
    marginal = bonus_case(4000, 600, 0.029)
    assert marginal["fee"] == 116.0 and marginal["worthIt"] is True


def test_the_advisory_never_tells_you_to_put_rent_on_a_card():
    from app.agents.advisory import AdvisoryAgent

    class Runtime:
        available = True
        def structured(self, *args, **kwargs):
            from app.agents.advisory import AdvisoryWordingOutput
            return AdvisoryWordingOutput(recommendations=[])

    from app.agents.strategy import StrategyAgent
    wallet, rules = _wallet_and_rules()
    strategy = StrategyAgent().run([_tx("Rent", "6513", 2150.0, "r")], wallet, rules)
    advice = AdvisoryAgent(Runtime()).run(strategy, {}, wallet)

    routing = [item for item in advice if item["id"].startswith("rec-bill-")]
    assert len(routing) == 1
    assert "cannot earn rewards" in routing[0]["headline"]
    # And nothing else in the list tells you to put rent on a card.
    assert not any("rent" in item["headline"].lower() and "use " in item["headline"].lower()
                   for item in advice)
