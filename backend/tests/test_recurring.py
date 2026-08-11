from datetime import date, timedelta
from math import sqrt

import pytest

from app.agents.forecast import ForecastAgent, add_months
from app.agents.recurring import (
    commitments,
    detect_streams,
    normalise_merchant,
    occurrences_between,
    split_history,
)

TODAY = date(2026, 8, 11)


def charge(days_ago, merchant, amount, category="Streaming", mcc="5815"):
    return {
        "id": f"{merchant}-{days_ago}",
        "date": str(TODAY - timedelta(days=days_ago)),
        "merchant": merchant,
        "amount": amount,
        "category": category,
        "mcc": mcc,
        "isPurchase": True,
        "pending": False,
    }


# -- merchant keys ----------------------------------------------------------

def test_a_merchant_key_survives_a_changing_reference():
    assert normalise_merchant("NETFLIX 8H2KQ") == normalise_merchant("NETFLIX 4B1XZ")
    assert normalise_merchant("STARBUCKS #1147") == normalise_merchant("STARBUCKS #0392")


def test_a_merchant_that_is_only_digits_keeps_them():
    """Dropping digit tokens from "76" would leave nothing to match on."""
    assert normalise_merchant("76") == "76"


def test_a_brand_with_a_digit_still_keys_consistently():
    """The key need not be pretty, only stable across the varying part."""
    assert normalise_merchant("7-ELEVEN 22841") == normalise_merchant("7-Eleven #109")


# -- detection --------------------------------------------------------------

def test_a_monthly_bill_is_detected_with_its_cadence():
    transactions = [charge(days, "GREYSTONE PROPERTY", 2200.0, "Rent", "6513") for days in (1, 31, 61)]

    streams = detect_streams(transactions, today=TODAY)

    assert len(streams) == 1
    assert streams[0]["cadence"] == "monthly"
    assert streams[0]["amount"] == 2200.0
    assert streams[0]["monthlyAmount"] == 2200.0
    assert streams[0]["confidence"] == "high"


def test_a_weekly_stream_becomes_more_than_four_charges_a_month():
    """52 weeks over 12 months is 4.33 charges, not 4 — a month is not four weeks."""
    transactions = [charge(days * 7 + 2, "MTA SUBWAY", 34.0, "Transit", "4111") for days in range(6)]

    stream = detect_streams(transactions, today=TODAY)[0]

    assert stream["cadence"] == "weekly"
    assert stream["monthlyAmount"] == pytest.approx(34.0 * 52 / 12, abs=0.01)


def test_charges_at_irregular_gaps_are_not_a_stream():
    """Three visits to one shop is a habit with a coincidence in it."""
    transactions = [charge(days, "RANDOM BODEGA", 20.0, "Groceries", "5411") for days in (3, 4, 40)]

    assert detect_streams(transactions, today=TODAY) == []


def test_charges_with_unstable_amounts_are_not_a_stream():
    transactions = [
        charge(1, "CORNER STORE", 12.0), charge(31, "CORNER STORE", 90.0),
        charge(61, "CORNER STORE", 45.0),
    ]

    assert detect_streams(transactions, today=TODAY) == []


def test_a_utility_bill_that_moves_with_the_season_is_still_a_stream():
    transactions = [
        charge(1, "CON EDISON", 128.0, "Utilities", "4900"),
        charge(31, "CON EDISON", 79.0, "Utilities", "4900"),
        charge(61, "CON EDISON", 104.0, "Utilities", "4900"),
    ]

    streams = detect_streams(transactions, today=TODAY)

    assert len(streams) == 1
    # Real variation, reported at lower confidence rather than withheld.
    assert streams[0]["confidence"] == "medium"


def test_a_cancelled_subscription_is_not_projected_forward():
    """Two charges last spring must not become eleven more this year."""
    transactions = [charge(days, "OLD GYM", 45.0, "Fitness", "7997") for days in (120, 150, 180)]

    assert detect_streams(transactions, today=TODAY) == []


def test_a_single_charge_is_never_a_stream():
    assert detect_streams([charge(3, "ONE OFF", 500.0)], today=TODAY) == []


def test_two_charges_are_reported_at_low_confidence():
    transactions = [charge(days, "SPOTIFY", 11.99) for days in (2, 32)]

    stream = detect_streams(transactions, today=TODAY)[0]

    assert stream["occurrences"] == 2
    assert stream["confidence"] == "low"


def test_two_charges_on_one_day_are_one_event():
    """A split payment is not evidence of a daily subscription."""
    transactions = [
        charge(1, "GREYSTONE", 1100.0, "Rent", "6513"),
        {**charge(1, "GREYSTONE", 1100.0, "Rent", "6513"), "id": "second"},
        charge(31, "GREYSTONE", 2200.0, "Rent", "6513"),
        charge(61, "GREYSTONE", 2200.0, "Rent", "6513"),
    ]

    stream = detect_streams(transactions, today=TODAY)[0]

    assert stream["cadence"] == "monthly"
    assert stream["amount"] == 2200.0


def test_refunds_and_transfers_never_form_a_stream():
    transactions = [
        {**charge(1, "PAYROLL", 3000.0), "isPurchase": False},
        {**charge(31, "PAYROLL", 3000.0), "isPurchase": False},
        {**charge(2, "RETURNS", -40.0), "isRefund": True},
        {**charge(32, "RETURNS", -40.0), "isRefund": True},
    ]

    assert detect_streams(transactions, today=TODAY) == []


# -- projecting a stream ----------------------------------------------------

def test_occurrences_land_on_billing_dates_not_a_pro_rata_share():
    stream = {"lastSeen": "2026-08-01", "intervalDays": 30}

    dates = occurrences_between(stream, date(2026, 8, 2), date(2026, 11, 1))

    assert [str(when) for when in dates] == ["2026-08-31", "2026-09-30", "2026-10-30"]


def test_history_splits_without_losing_or_duplicating_a_transaction():
    transactions = [charge(days, "NETFLIX", 15.49) for days in (1, 31, 61)]
    transactions += [charge(days, f"CAFE {days}", 8.0, "Dining", "5812") for days in (2, 5, 9)]
    streams = detect_streams(transactions, today=TODAY)

    committed, variable = split_history(transactions, streams, today=TODAY)

    assert len(committed) == 3
    assert len(variable) == 3
    assert len(committed) + len(variable) == len(transactions)


# -- the forecast on top of it ---------------------------------------------

def _history():
    rows = [charge(days, "GREYSTONE PROPERTY", 2200.0, "Rent", "6513") for days in (1, 31, 61)]
    rows += [charge(days * 3 + 1, f"CAFE {days}", 30.0, "Dining", "5812") for days in range(20)]
    return rows


def test_a_commitment_is_not_also_counted_as_variable_spending():
    """The double-count that makes a naive monthly forecast wrong."""
    rent_only = [charge(days, "GREYSTONE PROPERTY", 2200.0, "Rent", "6513") for days in (1, 31, 61)]

    result = ForecastAgent().run(rent_only, [], today=TODAY, horizon_months=1)

    assert result["recurringSpend"] == 2200.0
    assert result["variableSpend"] == 0.0
    assert result["projectedSpend"] == 2200.0


@pytest.mark.parametrize("months", [1, 3, 6, 12])
def test_the_horizon_is_a_calendar_span(months):
    result = ForecastAgent().run(_history(), [], today=TODAY, horizon_months=months)

    expected = (add_months(TODAY, months) - TODAY).days
    assert result["horizonMonths"] == months
    assert result["horizonDays"] == expected


@pytest.mark.parametrize("months", [1, 3, 12])
def test_the_monthly_buckets_account_for_the_whole_projection(months):
    result = ForecastAgent().run(_history(), [], today=TODAY, horizon_months=months)

    assert len(result["months"]) == months
    assert sum(bucket["total"] for bucket in result["months"]) == pytest.approx(
        result["projectedSpend"], abs=0.05 * months
    )
    assert result["months"][-1]["cumulative"] == pytest.approx(result["projectedSpend"], abs=0.05 * months)


@pytest.mark.parametrize("months", [1, 3, 12])
def test_the_category_breakdown_accounts_for_the_whole_projection(months):
    """A breakdown that does not sum to the total is worse than no breakdown."""
    result = ForecastAgent().run(_history(), [], today=TODAY, horizon_months=months)

    assert sum(row["projected"] for row in result["categories"]) == pytest.approx(
        result["projectedSpend"], abs=0.05 * len(result["categories"])
    )
    assert sum(row["share"] for row in result["categories"]) == pytest.approx(1.0, abs=0.001)


def test_the_three_sources_add_up_to_the_projection():
    planned = [{"id": "p", "kind": "purchase", "label": "Laptop", "startDate": str(TODAY + timedelta(days=10)),
                "amount": 1800, "categories": ["Electronics"]}]

    result = ForecastAgent().run(_history(), planned, today=TODAY, horizon_months=3)

    assert result["variableSpend"] + result["recurringSpend"] + result["plannedSpend"] == pytest.approx(
        result["projectedSpend"], abs=0.01
    )
    assert result["baselineSpend"] == pytest.approx(
        result["variableSpend"] + result["recurringSpend"], abs=0.01
    )


def test_a_planned_purchase_is_split_across_the_categories_it_touches():
    planned = [{"id": "trip", "kind": "event", "label": "Tokyo", "startDate": str(TODAY + timedelta(days=5)),
                "amount": 3000, "categories": ["Air travel", "Hotels", "Dining"]}]

    result = ForecastAgent().run([], planned, today=TODAY, horizon_months=1)

    by_category = {row["category"]: row["planned"] for row in result["categories"]}
    assert by_category["Air travel"] == 1000.0
    assert by_category["Hotels"] == 1000.0
    assert by_category["Dining"] == 1000.0


def test_the_range_widens_faster_than_square_root_scaling():
    """The naive band understates a long horizon, and this is by how much.

    A forecaster that only counts day-to-day noise scales its range with the
    square root of the horizon. That ignores the error in the daily mean, which
    was estimated from finite history and grows with the horizon itself. Twelve
    months out, counting both roughly doubles the honest range.
    """
    agent = ForecastAgent()
    one = agent.run(_history(), [], today=TODAY, horizon_months=1)
    twelve = agent.run(_history(), [], today=TODAY, horizon_months=12)

    naive = one["confidence"] * sqrt(twelve["horizonDays"] / one["horizonDays"])
    assert twelve["confidence"] > naive * 1.5


def test_a_horizon_beyond_the_history_is_labelled_an_extrapolation():
    thin = [charge(days, f"CAFE {days}", 20.0, "Dining", "5812") for days in range(0, 20, 2)]

    near = ForecastAgent().run(thin, [], today=TODAY, horizon_months=1)
    far = ForecastAgent().run(thin, [], today=TODAY, horizon_months=12)

    assert near["extrapolated"] is False
    assert far["extrapolated"] is True
    assert "extrapolated" in far["basis"]
    assert any("extrapolation" in note for note in ForecastAgent().degraded(far))


@pytest.mark.parametrize("given,expected", [(0, 1), (-4, 1), (99, 12), ("3", 3), (None, 1)])
def test_an_out_of_range_horizon_is_clamped_rather_than_refused(given, expected):
    result = ForecastAgent().run(_history(), [], today=TODAY, horizon_months=given)

    assert result["horizonMonths"] == expected


def test_an_empty_account_projects_nothing_without_crashing():
    result = ForecastAgent().run([], [], today=TODAY, horizon_months=6)

    assert result["projectedSpend"] == 0.0
    assert result["quality"] == "none"
    assert result["reliableMonths"] == 0
    assert result["months"] == [] or all(bucket["total"] == 0 for bucket in result["months"])


# -- the committed half is not certain either -------------------------------

def test_a_detected_commitment_carries_uncertainty():
    """Treating a stream as certain claimed half a percent on a year's spend."""
    rent = [charge(days, "GREYSTONE PROPERTY", 2200.0, "Rent", "6513") for days in (1, 31, 61)]

    result = ForecastAgent().run(rent, [], today=TODAY, horizon_months=12)

    assert result["variableSpend"] == 0.0
    assert result["confidence"] > 0
    # A year of rent is not knowable to within a few percent.
    assert result["confidence"] / result["projectedSpend"] > 0.05


def test_a_stream_seen_only_twice_widens_the_range_more_than_a_confirmed_one():
    confirmed = [charge(days, "GREYSTONE", 900.0, "Rent", "6513") for days in (1, 31, 61)]
    glimpsed = [charge(days, "GREYSTONE", 900.0, "Rent", "6513") for days in (1, 31)]
    agent = ForecastAgent()

    strong = agent.run(confirmed, [], today=TODAY, horizon_months=6)
    weak = agent.run(glimpsed, [], today=TODAY, horizon_months=6)

    assert strong["recurring"][0]["confidence"] == "high"
    assert weak["recurring"][0]["confidence"] == "low"
    assert weak["confidence"] > strong["confidence"]


def test_the_committed_range_widens_with_the_horizon():
    rent = [charge(days, "GREYSTONE", 900.0, "Rent", "6513") for days in (1, 31, 61)]
    agent = ForecastAgent()

    near = agent.run(rent, [], today=TODAY, horizon_months=1)
    far = agent.run(rent, [], today=TODAY, horizon_months=12)

    assert far["confidence"] / far["projectedSpend"] > near["confidence"] / near["projectedSpend"]


def test_a_display_name_keeps_the_capitals_it_was_given():
    """Stripping them turned "United Airlines" into "nited irlines"."""
    transactions = [charge(days, "United Airlines", 500.0, "Air travel", "4511") for days in (1, 31, 61)]

    stream = detect_streams(transactions, today=TODAY)[0]

    assert stream["merchant"] == "United Airlines"


# -- a habit is not a commitment --------------------------------------------

def test_a_restaurant_charging_the_same_amount_monthly_is_not_a_commitment():
    """The Plaid sandbox replays one basket monthly; four merchants at $500.

    From the numbers alone this is indistinguishable from a subscription. What
    separates them is what the merchant is: a landlord bills monthly by
    arrangement, a fried chicken shop does not.
    """
    transactions = [charge(days, "KFC", 500.0, "Dining", "5814") for days in (1, 31, 61)]

    stream = detect_streams(transactions, today=TODAY)[0]

    assert stream["kind"] == "habit"
    assert commitments([stream]) == []


def test_a_gym_charging_the_same_amount_monthly_is_a_commitment():
    transactions = [charge(days, "TOUCHSTONE CLIMBING", 78.5, "Fitness", "7997") for days in (1, 31, 61)]

    stream = detect_streams(transactions, today=TODAY)[0]

    assert stream["kind"] == "bill"
    assert len(commitments([stream])) == 1


def test_a_habit_still_counts_as_spending():
    """Excluding it from commitments must not delete it from the forecast."""
    kfc = [charge(days, "KFC", 500.0, "Dining", "5814") for days in (1, 31, 61)]

    result = ForecastAgent().run(kfc, [], today=TODAY, horizon_months=1)

    assert result["recurringSpend"] == 0.0
    assert result["variableSpend"] > 0
    assert result["projectedSpend"] > 0


def test_a_habit_is_projected_with_a_wider_range_than_a_bill():
    """Same money, different certainty — which is the point of the split."""
    habit = [charge(days, "KFC", 500.0, "Dining", "5814") for days in (1, 31, 61)]
    bill = [charge(days, "GREYSTONE", 500.0, "Rent", "6513") for days in (1, 31, 61)]
    agent = ForecastAgent()

    loose = agent.run(habit, [], today=TODAY, horizon_months=6)
    firm = agent.run(bill, [], today=TODAY, horizon_months=6)

    assert loose["confidence"] > firm["confidence"]


def test_a_habit_is_still_reported_so_the_user_can_see_it():
    transactions = [charge(days, "KFC", 500.0, "Dining", "5814") for days in (1, 31, 61)]

    result = ForecastAgent().run(transactions, [], today=TODAY, horizon_months=1)

    assert [s["kind"] for s in result["recurring"]] == ["habit"]
    assert "habit is not a commitment" in result["basis"]


def test_semi_monthly_billing_is_a_cadence_not_an_irregularity():
    """Paid on the 1st and the 15th, the gaps alternate rather than repeat."""
    transactions = [charge(days, "CITY PARKING", 60.0, "Services", "7523")
                    for days in (2, 18, 32, 48, 62)]

    stream = detect_streams(transactions, today=TODAY)[0]

    assert stream["cadence"] in {"semi-monthly", "fortnightly"}
    assert stream["monthlyAmount"] >= 120.0
