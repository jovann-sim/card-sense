from datetime import date, timedelta
from math import sqrt
from statistics import pstdev

import pytest

from app.agents.forecast import ForecastAgent


def test_trailing_history_zero_fills_days_and_uses_observed_variability():
    agent = ForecastAgent()
    transactions = [
        {"date": "2026-08-01", "amount": 100, "isPurchase": True},
        {"date": "2026-08-10", "amount": 100, "isPurchase": True},
        {"date": "2026-08-09", "amount": 500, "isPurchase": False},
        {"date": "2026-08-09", "amount": 50, "isPurchase": True, "pending": True},
        {"date": "2026-08-11", "amount": 900, "isPurchase": True},
        {"date": "not-a-date", "amount": 900, "isPurchase": True},
    ]

    result = agent.run(transactions, [], today=date(2026, 8, 10))

    samples = [100, *([0] * 8), 100]
    assert result["historyDays"] == 10
    assert result["quality"] == "limited"
    assert result["baselineSpend"] == 600
    assert result["projectedSpend"] == 600
    assert result["confidence"] == round(max(1.28 * pstdev(samples) * sqrt(30), 180), 2)


def test_planned_spend_counts_full_amount_only_when_start_is_in_horizon():
    agent = ForecastAgent()
    today = date(2026, 8, 10)
    planned = [
        {"id": "today", "kind": "purchase", "label": "Today", "startDate": today, "amount": 100, "categories": ["Dining"]},
        {"id": "last", "kind": "event", "label": "Last day", "startDate": today + timedelta(days=29), "amount": 200, "categories": ["Travel"]},
        {"id": "outside", "kind": "purchase", "label": "Outside", "startDate": today + timedelta(days=30), "amount": 300, "categories": ["Online retail"]},
    ]

    result = agent.run([], planned, today=today)

    assert result["baselineSpend"] == 0
    assert result["plannedSpend"] == 300
    assert result["projectedSpend"] == 300
    assert result["quality"] == "none"
    assert [entry["title"] for entry in result["timeline"]] == ["Today", "Last day"]


def test_cap_collision_and_card_state_use_real_cycle_spend():
    agent = ForecastAgent()
    wallet = [
        {"cardId": "a", "name": "Bonus", "last4": "1111", "network": "Visa", "track": "cashback", "accountId": "acct-a", "parseStatus": "parsed"},
        {"cardId": "b", "name": "Backup", "last4": "2222", "network": "Visa", "track": "cashback", "accountId": "acct-b", "parseStatus": "parsed"},
    ]
    rules = {
        "a": [{"id": "dining", "categoryLabel": "Dining", "rate": "5%", "valuePerDollar": 0.05, "capSpend": 600, "cycleLabel": "per month"}],
        "b": [{"id": "base", "categoryLabel": "Everything else", "rate": "2%", "valuePerDollar": 0.02, "capSpend": None, "cycleLabel": "no cap"}],
    }
    transactions = [
        {"date": "2026-08-02", "amount": 550, "category": "Dining", "accountId": "acct-a", "isPurchase": True},
        {"date": "2026-07-31", "amount": 400, "category": "Dining", "accountId": "acct-a", "isPurchase": True},
    ]
    planned = [{"id": "meal", "kind": "purchase", "label": "Dinner", "startDate": "2026-08-20", "amount": 100, "categories": ["Dining"]}]

    forecast = agent.run(transactions, planned, wallet, rules, today=date(2026, 8, 10))
    cards = agent.project_cards(transactions, wallet, rules, today=date(2026, 8, 10))

    cap = next(entry for entry in forecast["timeline"] if entry["kind"] == "cap")
    assert cap["title"] == "Dining passes Bonus's cap"
    assert "50.00 on Bonus" in cap["action"]
    assert "Backup" in cap["action"]
    assert cards[0]["cycleSpend"] == 550
    assert cards[0]["state"] == "approaching"


def test_conditional_rule_is_not_used_for_planned_cap_advice():
    agent = ForecastAgent()
    wallet = [{"cardId": "a", "name": "Conditional", "last4": "1111", "network": "Visa", "track": "cashback", "accountId": "acct-a", "parseStatus": "parsed"}]
    rules = {"a": [{
        "categoryLabel": "Dining", "rate": "10%", "valuePerDollar": 0.10,
        "capSpend": 50, "cycleLabel": "per month",
        "conditions": [{"kind": "enrolment", "description": "Activation required"}],
    }]}
    planned = [{"kind": "purchase", "label": "Dinner", "startDate": "2026-08-20", "amount": 100, "categories": ["Dining"]}]

    result = agent.run([], planned, wallet, rules, today=date(2026, 8, 10))

    assert [entry["kind"] for entry in result["timeline"]] == ["purchase"]


@pytest.mark.parametrize(
    ("cycle_label", "inside_date", "outside_date"),
    [
        ("per quarter", "2026-07-01", "2026-06-30"),
        ("per year", "2026-01-01", "2025-12-31"),
    ],
)
def test_card_cap_state_respects_quarter_and_year_boundaries(cycle_label, inside_date, outside_date):
    agent = ForecastAgent()
    wallet = [{
        "cardId": "card", "name": "Card", "last4": "1111", "network": "Visa",
        "track": "cashback", "accountId": "account", "parseStatus": "parsed",
    }]
    rules = {"card": [{
        "categoryLabel": "Dining", "rate": "5%", "capSpend": 100,
        "cycleLabel": cycle_label,
    }]}
    transactions = [
        {"date": inside_date, "amount": 80, "category": "Dining", "accountId": "account", "isPurchase": True},
        {"date": outside_date, "amount": 80, "category": "Dining", "accountId": "account", "isPurchase": True},
    ]

    cards = agent.project_cards(transactions, wallet, rules, today=date(2026, 8, 10))

    assert cards[0]["cycleSpend"] == 80
    assert cards[0]["state"] == "approaching"


def test_statement_cycle_is_explicitly_unverified():
    wallet = [{
        "cardId": "card", "name": "Card", "last4": "1111", "network": "Visa",
        "track": "cashback", "accountId": "account", "parseStatus": "parsed",
    }]
    rules = {"card": [{
        "categoryLabel": "Dining", "rate": "5%", "capSpend": 100,
        "cycleLabel": "per statement",
    }]}

    card = ForecastAgent().project_cards([], wallet, rules, today=date(2026, 8, 10))[0]

    assert card["state"] == "unverified"
    assert "statement boundary" in card["note"]


def test_earlier_plans_consume_cap_headroom_for_later_plans():
    agent = ForecastAgent()
    wallet = [{
        "cardId": "card", "name": "Bonus", "last4": "1111", "network": "Visa",
        "track": "cashback", "accountId": "account", "parseStatus": "parsed",
    }]
    rules = {"card": [{
        "id": "dining", "categoryLabel": "Dining", "rate": "5%",
        "capSpend": 100, "cycleLabel": "per month",
    }]}
    planned = [
        {"id": "first", "kind": "purchase", "label": "First", "startDate": "2026-08-15", "amount": 70, "categories": ["Dining"]},
        {"id": "second", "kind": "purchase", "label": "Second", "startDate": "2026-08-20", "amount": 50, "categories": ["Dining"]},
    ]

    result = agent.run([], planned, wallet, rules, today=date(2026, 8, 10))

    cap = next(entry for entry in result["timeline"] if entry["kind"] == "cap")
    assert cap["date"] == "2026-08-20"
    assert "30.00 on Bonus" in cap["action"]


def test_observed_leakage_rate_prices_cost_of_doing_nothing():
    result = ForecastAgent().run(
        [{"date": "2026-08-10", "amount": 100, "isPurchase": True}],
        [],
        today=date(2026, 8, 10),
        leakage_rate=0.04,
    )

    assert result["projectedSpend"] == 3000
    assert result["doNothingCost"] == 120
