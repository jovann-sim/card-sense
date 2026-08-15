from datetime import date

import pytest

from app.agents.strategy import StrategyAgent
from app.catalog_seed import CATALOG, rules_for
from app.simulation import (
    card_additions,
    observed_days,
    optimal_value,
    plan,
    routing_gains,
)

TODAY = date(2026, 8, 16)


def tx(category, mcc, amount, day, account="a", tid=None):
    return {"id": tid or f"{category}-{day}-{amount}", "date": f"2026-{day}",
            "merchant": category, "amount": amount, "category": category,
            "mcc": mcc, "isPurchase": True, "accountId": account}


def year_of(category, mcc, monthly, account="a"):
    return [tx(category, mcc, monthly, f"{m:02d}-05", account, f"{category}-{m}")
            for m in range(1, 13)]


GROCERY_CARD = {"cardId": "blue", "name": "Blue Cash", "last4": "1111", "network": "Amex",
                "track": "cashback", "accountId": "a", "parseStatus": "parsed"}
GROCERY_RULES = [
    {"id": "g", "categoryLabel": "U.S. Supermarkets", "rate": "6%", "valuePerDollar": 0.06,
     "mccCodes": ["5411", "5422", "5451", "5499"]},
    {"id": "b", "categoryLabel": "Everything else", "rate": "1%", "valuePerDollar": 0.01, "mccCodes": []},
]
DINING_CARD = {"cardId": "jrny", "name": "Journey", "last4": "2222", "network": "Visa",
               "track": "cashback", "accountId": "b", "parseStatus": "parsed"}
DINING_RULES = [
    {"id": "d", "categoryLabel": "Dining", "rate": "4%", "valuePerDollar": 0.04,
     "mccCodes": ["5811", "5812", "5813", "5814"]},
    {"id": "b2", "categoryLabel": "Everything else", "rate": "1%", "valuePerDollar": 0.01, "mccCodes": []},
]


def catalog():
    return [{**entry, "rules": rules_for(entry)} for entry in CATALOG]


# -- the window everything is annualised against ----------------------------

def test_the_observed_window_is_measured_not_assumed():
    rows = [tx("Dining", "5812", 10, "01-01"), tx("Dining", "5812", 10, "12-31")]
    assert observed_days(rows) == 365


def test_an_empty_history_has_no_window():
    assert observed_days([]) == 0


# -- multi-card allocation --------------------------------------------------

def test_two_cards_beat_either_one_alone():
    """The point of a wallet: each category goes where it earns most."""
    agent = StrategyAgent()
    rows = year_of("Groceries", "5411", 400) + year_of("Dining", "5812", 300, "b")
    rules = {"blue": GROCERY_RULES, "jrny": DINING_RULES}

    grocery_only = optimal_value(agent, rows, [GROCERY_CARD], rules)
    dining_only = optimal_value(agent, rows, [DINING_CARD], rules)
    both = optimal_value(agent, rows, [GROCERY_CARD, DINING_CARD], rules)

    assert both > grocery_only
    assert both > dining_only
    # 6% of groceries plus 4% of dining, not one rate applied to everything.
    assert both == pytest.approx(400 * 12 * 0.06 + 300 * 12 * 0.04, abs=0.5)


def test_a_cap_pushes_the_overflow_onto_the_second_card():
    agent = StrategyAgent()
    rows = year_of("Groceries", "5411", 1000)
    capped = [
        {**GROCERY_RULES[0], "capSpend": 6000, "cycleLabel": "per year"},
        GROCERY_RULES[1],
    ]
    rules = {"blue": capped, "jrny": [
        {"id": "flat", "categoryLabel": "Everything else", "rate": "2%",
         "valuePerDollar": 0.02, "mccCodes": []}]}

    value = optimal_value(agent, rows, [GROCERY_CARD, DINING_CARD], rules)

    # 6% on the first 6,000, then 2% on the remaining 6,000 — not 6% throughout
    # and not 1% once the cap is gone.
    assert value == pytest.approx(6000 * 0.06 + 6000 * 0.02, abs=0.5)


def test_the_plan_groups_moves_by_the_card_they_point_at():
    """Eight lines saying "move this to that card" is one decision."""
    agent = StrategyAgent()
    rows = year_of("Dining", "5812", 300) + year_of("Transit", "4111", 200)
    rules = {"blue": GROCERY_RULES, "jrny": [
        {"id": "d", "categoryLabel": "Dining", "rate": "4%", "valuePerDollar": 0.04, "mccCodes": ["5812"]},
        {"id": "t", "categoryLabel": "Transit", "rate": "4%", "valuePerDollar": 0.04, "mccCodes": ["4111"]},
        {"id": "b2", "categoryLabel": "Everything else", "rate": "1%", "valuePerDollar": 0.01, "mccCodes": []}]}

    result = plan(agent, rows, [GROCERY_CARD, DINING_CARD], rules, [], [], [])
    moves = [step for step in result["steps"] if step["kind"] == "reassign"]

    assert len(moves) == 1
    assert len(moves[0]["categories"]) == 2
    assert moves[0]["card"] == "Journey"


# -- cards the user does not hold -------------------------------------------

def test_a_card_is_priced_by_what_it_adds_not_what_it_advertises():
    """A 4x dining card is worth nothing to someone who already has one."""
    agent = StrategyAgent()
    rows = year_of("Dining", "5812", 500)
    already = {"jrny": [
        {"id": "d", "categoryLabel": "Dining", "rate": "10%", "valuePerDollar": 0.10, "mccCodes": ["5812"]},
        {"id": "b2", "categoryLabel": "Everything else", "rate": "1%", "valuePerDollar": 0.01, "mccCodes": []}]}

    additions = card_additions(agent, rows, [DINING_CARD], already, catalog(), days=365)
    gold = next(row for row in additions if row["card"] == "American Express Gold")

    assert gold["rewardPerYear"] == 0.0


def test_an_annual_fee_can_make_a_better_card_a_worse_deal():
    agent = StrategyAgent()
    rows = year_of("Dining", "5812", 200)

    additions = card_additions(agent, rows, [GROCERY_CARD], {"blue": GROCERY_RULES}, catalog(), days=365)
    gold = next(row for row in additions if row["card"] == "American Express Gold")

    assert gold["rewardPerYear"] > 0          # it does earn more
    assert gold["netOngoing"] < 0             # and still loses to the fee
    assert gold["worthIt"] is False


def test_a_free_card_that_adds_anything_is_worth_it():
    agent = StrategyAgent()
    rows = year_of("Fashion", "5651", 800)

    additions = card_additions(agent, rows, [GROCERY_CARD], {"blue": GROCERY_RULES}, catalog(), days=365)
    flat = next(row for row in additions if row["card"] == "Wells Fargo Active Cash")

    assert flat["annualFee"] == 0
    assert flat["netOngoing"] == flat["rewardPerYear"] > 0
    assert flat["worthIt"] is True


def test_the_first_year_and_every_year_after_are_reported_separately():
    """A bonus covering a fee once does not make the card worth keeping."""
    agent = StrategyAgent()
    rows = year_of("Dining", "5812", 200)

    additions = card_additions(agent, rows, [GROCERY_CARD], {"blue": GROCERY_RULES}, catalog(), days=365)
    venture = next(row for row in additions if row["card"] == "Capital One Venture X")

    assert venture["netFirstYear"] > 0
    assert venture["netOngoing"] < 0
    assert venture["welcomeValue"] > 0


def test_a_card_already_held_is_never_offered():
    agent = StrategyAgent()
    held = [{**GROCERY_CARD, "name": "Wells Fargo Active Cash"}]

    additions = card_additions(agent, year_of("Dining", "5812", 100), held,
                               {"blue": GROCERY_RULES}, catalog(), days=365)

    assert "Wells Fargo Active Cash" not in {row["card"] for row in additions}


def test_the_recommendation_is_made_on_ongoing_value_not_the_bonus():
    """Otherwise it recommends a card that loses money every year but the first."""
    agent = StrategyAgent()
    rows = year_of("Dining", "5812", 200)

    result = plan(agent, rows, [GROCERY_CARD], {"blue": GROCERY_RULES}, catalog(), [], [])
    acquire = [step for step in result["steps"] if step["kind"] == "acquire"]

    assert len(acquire) <= 1
    if acquire:
        named = acquire[0]["title"]
        assert "Venture X" not in named


# -- routing, and the one time it wins --------------------------------------

def test_routing_for_ordinary_earn_never_reaches_the_plan():
    losing = [{"category": "Rent", "spend": 25800.0, "worthIt": False, "net": -345.72,
               "serviceName": "Plastiq", "verdict": "no", "bestCard": "Blue Cash",
               "fee": 748.2, "reward": 402.48}]

    assert routing_gains(losing, []) == []


def test_routing_to_reach_a_bonus_does():
    welcome = [{"card": "Sapphire", "gap": 2350.0, "deadline": "2026-09-08",
                "rescue": {"worthIt": True, "spendToRoute": 2350.0, "fee": 68.15,
                           "bonusValue": 720.0, "net": 651.85, "serviceName": "Plastiq"}}]

    gains = routing_gains([], welcome)

    assert len(gains) == 1
    assert gains[0]["kind"] == "welcome"
    assert gains[0]["net"] == 651.85


def test_the_plan_ranks_a_bonus_rescue_above_a_small_reassignment():
    agent = StrategyAgent()
    rows = year_of("Dining", "5812", 60)
    welcome = [{"card": "Sapphire", "gap": 2350.0, "deadline": "2026-09-08",
                "rescue": {"worthIt": True, "spendToRoute": 2350.0, "fee": 68.15,
                           "bonusValue": 720.0, "net": 651.85, "serviceName": "Plastiq"}}]

    result = plan(agent, rows, [GROCERY_CARD, DINING_CARD],
                  {"blue": GROCERY_RULES, "jrny": DINING_RULES}, [], [], welcome)

    assert result["steps"][0]["kind"] == "route-welcome"


# -- the whole plan ---------------------------------------------------------

def test_an_empty_account_produces_an_empty_plan_without_crashing():
    result = plan(StrategyAgent(), [], [], {}, [], [], [])

    assert result["steps"] == []
    assert result["observedDays"] == 0
    assert result["annualisedGap"] == 0.0


def test_every_step_carries_a_number_and_a_reason():
    agent = StrategyAgent()
    rows = year_of("Dining", "5812", 300) + year_of("Groceries", "5411", 400)

    result = plan(agent, rows, [GROCERY_CARD, DINING_CARD],
                  {"blue": GROCERY_RULES, "jrny": DINING_RULES}, catalog(), [], [])

    assert result["steps"]
    for step in result["steps"]:
        assert step["value"] > 0
        assert step["title"] and step["detail"]
        assert step["valueWindow"]
    ranks = [step["rank"] for step in result["steps"]]
    assert ranks == sorted(ranks)


def test_catalog_rules_are_priced_by_programme_not_by_track():
    """An Amex point is 2.1c; the generic "points" fallback prices it at 1.2.

    Falling back would have made every transferable-currency card look about
    forty percent worse than it is, which changes which card is recommended.
    """
    from app.valuations import REWARD_UNIT_VALUES

    sapphire = next(entry for entry in CATALOG if entry["id"] == "sapphire-preferred")
    dining = next(rule for rule in rules_for(sapphire) if rule["categoryLabel"] == "Dining")
    assert dining["valuePerDollar"] == pytest.approx(3.0 * REWARD_UNIT_VALUES["ultimate rewards"][0], abs=1e-6)

    gold = next(entry for entry in CATALOG if entry["id"] == "amex-gold")
    amex_dining = next(rule for rule in rules_for(gold) if rule["categoryLabel"] == "Dining")
    assert amex_dining["valuePerDollar"] == pytest.approx(4.0 * REWARD_UNIT_VALUES["membership rewards"][0], abs=1e-6)


def test_an_unpriced_programme_is_refused_rather_than_guessed():
    """A silent fallback changes which card the product recommends."""
    from app.catalog_seed import _value_per_dollar

    with pytest.raises(KeyError):
        _value_per_dollar("points", "a programme nobody has priced", 3.0)
