from datetime import date, timedelta

import pytest

from app.mcc import codes_for
from app.welcome import bonus_value, qualify_catalog, qualifying_spend, rescue, track_held

TODAY = date(2026, 8, 11)
BONUS = {"award": 60000, "unit": "points", "minSpend": 4000, "windowDays": 90}


def card(days_open=62):
    return {"cardId": "c", "name": "Sapphire Preferred", "accountId": "a",
            "track": "points", "openedAt": str(TODAY - timedelta(days=days_open))}


def spend(rows):
    return [{"id": str(i), "date": str(TODAY - timedelta(days=d)), "amount": amount,
             "accountId": acct, "category": cat, "isPurchase": purchase}
            for i, (d, amount, acct, cat, purchase) in enumerate(rows)]


# -- what counts ------------------------------------------------------------

def test_only_this_card_and_this_window_count():
    rows = spend([
        (10, 500.0, "a", "Dining", True),      # counts
        (10, 500.0, "b", "Dining", True),      # another card
        (200, 500.0, "a", "Dining", True),     # before the window
    ])
    total, count = qualifying_spend(rows, "a", TODAY - timedelta(days=62), TODAY)
    assert total == 500.0 and count == 1


def test_a_transfer_never_counts_toward_a_minimum():
    """Telling someone they qualified when the issuer disagrees costs them the bonus."""
    rows = spend([(5, 4000.0, "a", "Transfers & payments", True)])
    assert qualifying_spend(rows, "a", TODAY - timedelta(days=62), TODAY) == (0.0, 0)


def test_a_refund_reduces_qualifying_spend_as_issuers_do():
    rows = spend([(5, 1000.0, "a", "Fashion", True), (4, -400.0, "a", "Fashion", True)])
    total, count = qualifying_spend(rows, "a", TODAY - timedelta(days=62), TODAY)
    assert total == 600.0 and count == 1


def test_a_non_purchase_is_excluded():
    rows = spend([(5, 5000.0, "a", "Dining", False)])
    assert qualifying_spend(rows, "a", TODAY - timedelta(days=62), TODAY) == (0.0, 0)


# -- progress ---------------------------------------------------------------

def test_a_card_with_no_opening_date_is_not_guessed_at():
    """Without the window there is no deadline, and a wrong deadline is worse."""
    assert track_held({"cardId": "c", "name": "X", "accountId": "a"}, BONUS, []) is None


def test_falling_behind_the_pace_is_at_risk():
    rows = spend([(d, 55.0, "a", "Dining", True) for d in range(0, 60, 2)])
    progress = track_held(card(), BONUS, rows, today=TODAY)

    assert progress["state"] == "at-risk"
    assert progress["gap"] == pytest.approx(2350.0, abs=1)
    assert progress["perDayNeeded"] > progress["perDayCurrent"]


def test_keeping_the_pace_is_on_track():
    """Not yet there, but the current rate clears the gap before the deadline."""
    rows = spend([(d, 120.0, "a", "Dining", True) for d in range(0, 60, 2)])
    progress = track_held(card(), BONUS, rows, today=TODAY)

    assert progress["state"] == "on-track"
    assert progress["gap"] > 0
    assert progress["perDayCurrent"] * progress["daysLeft"] >= progress["gap"]


def test_clearing_the_minimum_is_met():
    rows = spend([(5, 4200.0, "a", "Dining", True)])
    progress = track_held(card(), BONUS, rows, today=TODAY)

    assert progress["state"] == "met"
    assert progress["gap"] == 0.0


def test_a_closed_window_is_missed_not_still_open():
    rows = spend([(100, 100.0, "a", "Dining", True)])
    assert track_held(card(days_open=120), BONUS, rows, today=TODAY)["state"] == "missed"


def test_the_award_is_priced_through_the_same_table_as_everything_else():
    from app.valuations import VALUATIONS
    assert bonus_value(BONUS) == pytest.approx(60000 * VALUATIONS["points"], abs=0.01)


# -- the one case where paying a fee wins -----------------------------------

def test_routing_to_save_a_bonus_is_worth_the_fee():
    """Losing trade for ordinary earn; good trade to buy a bonus."""
    rows = spend([(d, 55.0, "a", "Dining", True) for d in range(0, 60, 2)])
    saved = rescue(track_held(card(), BONUS, rows, today=TODAY))

    assert saved["worthIt"] is True
    assert saved["fee"] < saved["bonusValue"]
    assert saved["net"] > 500


def test_no_rescue_is_offered_once_the_bonus_is_met():
    rows = spend([(5, 4200.0, "a", "Dining", True)])
    assert rescue(track_held(card(), BONUS, rows, today=TODAY)) is None


def test_no_rescue_is_offered_once_the_window_has_closed():
    rows = spend([(100, 100.0, "a", "Dining", True)])
    assert rescue(track_held(card(days_open=120), BONUS, rows, today=TODAY)) is None


# -- would this spending clear a bonus at all -------------------------------

def test_a_bonus_out_of_reach_is_reported_as_such():
    """The question is not what the card pays but whether you would get it."""
    result = qualify_catalog({"name": "X", "track": "points"}, BONUS, 900.0)

    assert result["qualifies"] is False
    assert result["shortfall"] > 1_000
    assert result["monthsToMinimum"] > result["monthsAllowed"]


def test_a_bonus_within_reach_qualifies():
    result = qualify_catalog({"name": "X", "track": "points"}, BONUS, 1_800.0)

    assert result["qualifies"] is True
    assert result["monthsToMinimum"] < result["monthsAllowed"]


def test_no_spending_never_qualifies_and_does_not_divide_by_zero():
    result = qualify_catalog({"name": "X", "track": "points"}, BONUS, 0.0)

    assert result["qualifies"] is False
    assert result["monthsToMinimum"] is None


# -- the mcc specificity fix ------------------------------------------------

def test_a_specific_category_does_not_inherit_its_parent_codes():
    """A rule paying a bonus on flights must not pay it on a hotel."""
    air = codes_for("Air travel")

    assert "4511" in air
    assert "7011" not in air      # hotels
    assert "7512" not in air      # car rental


def test_a_compound_label_still_gets_both_halves():
    codes = codes_for("Air travel and hotels")

    assert "4511" in codes and "7011" in codes


def test_the_broad_label_still_gets_the_broad_list():
    assert set(codes_for("Travel")) >= {"4511", "7011", "7512"}
