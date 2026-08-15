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
    out = StrategyAgent().run([{
        "category": "Dining", "amount": 100, "accountId": "one", "date": "2026-08-10",
    }], wallet, rules)
    # The held A transaction earns 4% only on its first $50. The optimiser can
    # move the remainder to B; actual rewards may not ignore A's cap.
    assert out["captured"] == 2
    assert out["unclaimed"] == 2
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


def test_unverified_conditions_do_not_inflate_available_rewards():
    wallet = [{
        "cardId": "conditional", "name": "Conditional", "last4": "1111",
        "accountId": "one", "track": "cashback", "parseStatus": "parsed",
    }]
    rules = {"conditional": [
        {
            "categoryLabel": "Dining", "valuePerDollar": 0.05, "cap": None,
            "conditions": [{
                "kind": "transaction_count",
                "description": "Make five transactions in the statement period.",
            }],
        },
        {"categoryLabel": "Everything else", "valuePerDollar": 0.01, "cap": None},
    ]}

    result = StrategyAgent().run(
        [{"category": "Dining", "amount": 100, "accountId": "one", "date": "2026-08-10"}],
        wallet,
        rules,
    )

    assert result["captured"] == 1
    assert result["unclaimed"] == 0
    assert "conditional-rate" in result["categories"][0]["flags"]
    assert "five transactions" in result["categories"][0]["note"]


def test_merchant_rate_only_prices_matching_merchants():
    wallet = [{
        "cardId": "merchant", "name": "Merchant", "last4": "1111",
        "track": "cashback", "parseStatus": "parsed",
    }]
    rules = {"merchant": [
        {
            "categoryLabel": "Groceries", "valuePerDollar": 0.05, "cap": None,
            "merchants": ["Cold Storage"],
        },
        {"categoryLabel": "Everything else", "valuePerDollar": 0.01, "cap": None},
    ]}

    result = StrategyAgent().run([
        {"category": "Groceries", "merchant": "Cold Storage Holland Village", "amount": 100},
        {"category": "Groceries", "merchant": "FairPrice", "amount": 100},
    ], wallet, rules)

    assert result["unclaimed"] == 6


def test_channel_rate_requires_matching_transaction_evidence():
    wallet = [{
        "cardId": "online", "name": "Online", "last4": "1111",
        "track": "cashback", "parseStatus": "parsed",
    }]
    rules = {"online": [
        {
            "categoryLabel": "Retail", "valuePerDollar": 0.04, "cap": None,
            "channels": ["online"],
        },
        {"categoryLabel": "Everything else", "valuePerDollar": 0.01, "cap": None},
    ]}

    result = StrategyAgent().run([
        {"category": "Retail", "paymentChannel": "online", "amount": 100},
        {"category": "Retail", "paymentChannel": "in store", "amount": 100},
        {"category": "Retail", "amount": 100},
    ], wallet, rules)

    assert result["unclaimed"] == 6


def test_actual_rewards_step_down_after_the_cards_cap():
    wallet = [{
        "cardId": "capped", "name": "Capped", "last4": "1111",
        "accountId": "one", "track": "cashback", "parseStatus": "parsed",
    }]
    rules = {"capped": [
        {"categoryLabel": "Dining", "valuePerDollar": 0.05, "cap": 50, "cycleLabel": "per month"},
        {"categoryLabel": "Everything else", "valuePerDollar": 0.01, "cap": None},
    ]}

    result = StrategyAgent().run(
        [{"category": "Dining", "amount": 100, "accountId": "one", "date": "2026-08-10"}],
        wallet,
        rules,
    )

    assert result["captured"] == 3
    assert result["unclaimed"] == 0


@pytest.mark.parametrize(("cycle", "first", "second"), [
    ("per month", "2026-07-31", "2026-08-01"),
    ("per quarter", "2026-06-30", "2026-07-01"),
    ("per year", "2025-12-31", "2026-01-01"),
])
def test_caps_reset_at_calendar_cycle_boundaries(cycle, first, second):
    wallet = [{
        "cardId": "capped", "name": "Capped", "last4": "1111",
        "accountId": "one", "track": "cashback", "parseStatus": "parsed",
    }]
    rules = {"capped": [
        {"categoryLabel": "Dining", "valuePerDollar": 0.05, "cap": 100, "cycleLabel": cycle},
        {"categoryLabel": "Everything else", "valuePerDollar": 0.01, "cap": None},
    ]}

    result = StrategyAgent().run([
        {"category": "Dining", "amount": 100, "accountId": "one", "date": first},
        {"category": "Dining", "amount": 100, "accountId": "one", "date": second},
    ], wallet, rules)

    assert result["captured"] == 10
    assert result["unclaimed"] == 0


def test_a_cap_is_shared_by_transactions_inside_the_same_period():
    wallet = [{
        "cardId": "capped", "name": "Capped", "last4": "1111",
        "accountId": "one", "track": "cashback", "parseStatus": "parsed",
    }]
    rules = {"capped": [
        {"categoryLabel": "Dining", "valuePerDollar": 0.05, "cap": 100, "cycleLabel": "per month"},
        {"categoryLabel": "Everything else", "valuePerDollar": 0.01, "cap": None},
    ]}

    result = StrategyAgent().run([
        {"category": "Dining", "amount": 100, "accountId": "one", "date": "2026-08-01"},
        {"category": "Dining", "amount": 100, "accountId": "one", "date": "2026-08-20"},
    ], wallet, rules)

    assert result["captured"] == 6
    assert result["unclaimed"] == 0


def test_statement_cycle_caps_are_excluded_without_a_statement_boundary():
    wallet = [{
        "cardId": "statement", "name": "Statement", "last4": "1111",
        "accountId": "one", "track": "cashback", "parseStatus": "parsed",
    }]
    rules = {"statement": [
        {"categoryLabel": "Dining", "valuePerDollar": 0.05, "cap": 100, "cycleLabel": "per statement"},
        {"categoryLabel": "Everything else", "valuePerDollar": 0.01, "cap": None},
    ]}

    result = StrategyAgent().run([
        {"category": "Dining", "amount": 100, "accountId": "one", "date": "2026-08-10"},
    ], wallet, rules)

    assert result["captured"] == 1
    assert result["unclaimed"] == 0
    assert "conditional-rate" in result["categories"][0]["flags"]
    assert "statement cycle" in result["categories"][0]["note"]


def test_dated_cycle_caps_are_excluded_when_the_transaction_has_no_date():
    wallet = [{
        "cardId": "monthly", "name": "Monthly", "last4": "1111",
        "accountId": "one", "track": "cashback", "parseStatus": "parsed",
    }]
    rules = {"monthly": [
        {"categoryLabel": "Dining", "valuePerDollar": 0.05, "cap": 100, "cycleLabel": "per month"},
        {"categoryLabel": "Everything else", "valuePerDollar": 0.01, "cap": None},
    ]}

    result = StrategyAgent().run([
        {"category": "Dining", "amount": 100, "accountId": "one"},
    ], wallet, rules)

    assert result["captured"] == 1
    assert result["unclaimed"] == 0
    assert "conditional-rate" in result["categories"][0]["flags"]
    assert "transaction date" in result["categories"][0]["note"]
