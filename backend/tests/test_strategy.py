import pytest
from app.agents.strategy import StrategyAgent


def test_strategy_never_invents_actual_rewards_for_unassigned_transactions():
    wallet = [{"cardId": "dining", "name": "Dining Card", "last4": "1234", "track": "cashback", "parseStatus": "parsed"}]
    rules = {"dining": [{"categoryLabel": "Dining", "rate": "4%", "cap": None, "cycleLabel": "no cap"}]}
    out = StrategyAgent().run([{"category": "Dining", "amount": 100}], wallet, rules)
    assert out["captured"] == 0
    assert out["unclaimed"] == 4
    assert out["categories"][0]["usedCard"] == "Unassigned"
    assert out["categories"][0]["flags"] == ["rules-unverified"]


def test_strategy_respects_cap_and_detects_ties():
    wallet = [
        {"cardId": "a", "name": "A", "last4": "1111", "accountId": "one", "track": "cashback", "parseStatus": "parsed"},
        {"cardId": "b", "name": "B", "last4": "2222", "track": "cashback", "parseStatus": "parsed"},
    ]
    rules = {
        "a": [{"categoryLabel": "Dining", "rate": "4%", "cap": 50, "cycleLabel": "quarter"}],
        "b": [{"categoryLabel": "Dining", "rate": "4%", "cap": None, "cycleLabel": "no cap"}],
    }
    out = StrategyAgent().run([{"category": "Dining", "amount": 100, "accountId": "one"}], wallet, rules)
    assert out["captured"] == 4
    assert out["unclaimed"] == 0
    assert out["categories"][0]["note"].startswith("Tied with B")


def test_goal_projection_has_frontend_fields():
    goal = {"track": "points", "target": 1000, "unitLabel": "points", "current": 0, "deadline": None, "purpose": "trip"}
    out = StrategyAgent().goal_projection(goal, 10)
    # Pace is captured value divided by what one unit is worth, so derive the
    # expectation rather than pinning it to a valuation that will change.
    from app.valuations import VALUATIONS
    assert out["pacePerMonth"] == pytest.approx(round(10 / VALUATIONS["points"], 2))
    assert out["projectedAt"] is not None


def test_strategy_prices_each_mcc_inside_a_broad_category():
    wallet = [
        {"cardId": "flight", "name": "Flight", "last4": "1111", "track": "cashback", "parseStatus": "parsed"},
        {"cardId": "hotel", "name": "Hotel", "last4": "2222", "track": "cashback", "parseStatus": "parsed"},
    ]
    rules = {
        "flight": [{"categoryLabel": "Flights", "mccCodes": ["4511"], "valuePerDollar": 0.05,
                    "cap": None, "cycleLabel": "no cap"}],
        "hotel": [{"categoryLabel": "Hotels", "mccCodes": ["7011"], "valuePerDollar": 0.02,
                   "cap": None, "cycleLabel": "no cap"}],
    }
    transactions = [
        {"category": "Travel", "mcc": "4511", "amount": 100},
        {"category": "Travel", "mcc": "7011", "amount": 100},
    ]

    result = StrategyAgent().run(transactions, wallet, rules)

    assert result["unclaimed"] == 7
    assert len(result["categories"]) == 1
