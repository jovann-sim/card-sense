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

def test_a_bare_list_from_the_model_is_accepted():
    """Asked for {"recommendations": [...]}, a model may return just the list."""
    from app.agents.advisory import AdvisoryAgent

    class Runtime:
        available = True
        def json(self, *args, **kwargs):
            return [{"headline": "Move dining", "impact": 5.0}]

    result = AdvisoryAgent(Runtime()).run({"categories": [], "unclaimed": 0}, {}, [])
    assert isinstance(result, list) and result[0]["id"] == "rec-0"


def test_a_malformed_model_response_does_not_take_down_the_run():
    """Deterministic figures must survive a bad advisory response."""
    from app.agents.advisory import AdvisoryAgent

    class Runtime:
        available = True
        def json(self, *args, **kwargs):
            return "not json at all"

    assert isinstance(AdvisoryAgent(Runtime()).run({"categories": [], "unclaimed": 0}, {}, []), list)
