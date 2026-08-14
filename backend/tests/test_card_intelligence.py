from __future__ import annotations

import pytest

from app.agents.card_intelligence import CardIntelligenceAgent, with_rule_ids
from app.agents.runtime import ModelUnavailable
from app.agents.schema import ExtractionResult, display_rate, value_per_dollar
from app.agents.strategy import StrategyAgent
from app.agents.terms import html_to_text


class FakeRuntime:
    """Stands in for Gemini so these tests never touch the network."""

    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def structured(self, prompt, schema, *, document=None, temperature=0.0):
        if self.error:
            raise self.error
        return self.result


def rule(**kwargs):
    """The flattened shape the pricing helpers operate on."""
    base = {
        "categoryLabel": "Dining", "rewardType": "cashback", "rateValue": 4.0,
        "rateUnit": "percent", "cap": None, "capType": None,
        "cycleLabel": "no cap", "minSpend": None, "notes": None,
    }
    return {**base, **kwargs}


def extracted(**kwargs):
    """The nested shape the model returns, with the rate inside `rewards`."""
    flat = rule(**kwargs)
    return {
        "categoryLabel": flat["categoryLabel"],
        "tier": kwargs.get("tier", "bonus"),
        "cap": flat["cap"], "capType": flat["capType"],
        "cycleLabel": flat["cycleLabel"], "minSpend": flat["minSpend"],
        "mccCodes": kwargs.get("mccCodes", []),
        "merchants": kwargs.get("merchants", []),
        "channels": kwargs.get("channels", []),
        "exclusions": kwargs.get("exclusions", []),
        "conditions": kwargs.get("conditions", []),
        "requiresSelection": kwargs.get("requiresSelection", False),
        "selectableCategories": kwargs.get("selectableCategories", []),
        "rewards": kwargs.get("rewards") or [{
            "rewardType": flat["rewardType"], "rateValue": flat["rateValue"],
            "rateUnit": flat["rateUnit"],
            "rewardCurrency": kwargs.get("rewardCurrency"),
        }],
    }


# -- pricing ----------------------------------------------------------------

def test_percentage_prices_as_a_fraction_of_the_dollar():
    assert value_per_dollar(rule(rateValue=4, rateUnit="percent")) == 0.04


def test_miles_price_through_the_reward_currency():
    """An unnamed programme falls back to the default miles valuation."""
    from app.valuations import DEFAULT_UNIT_VALUES
    default, _ = DEFAULT_UNIT_VALUES["miles"]
    priced = value_per_dollar(rule(rewardType="miles", rateValue=1.4, rateUnit="miles_per_dollar"))
    assert priced == pytest.approx(1.4 * default)


def test_points_price_through_the_reward_currency():
    """Derived from the table, so confirming a valuation does not fail a test."""
    from app.valuations import DEFAULT_UNIT_VALUES
    default, _ = DEFAULT_UNIT_VALUES["points"]
    priced = value_per_dollar(rule(rewardType="points", rateValue=10, rateUnit="points_per_dollar"))
    assert priced == pytest.approx(10 * default)


def test_display_rate_reads_naturally_per_reward_type():
    assert display_rate(rule(rateValue=4, rateUnit="percent")) == "4% cash back"
    assert display_rate(rule(rateValue=1.4, rateUnit="miles_per_dollar")) == "1.4 mpd"
    assert display_rate(rule(rateValue=10, rateUnit="points_per_dollar")) == "10× points"


# -- strategy uses the number, not the prose --------------------------------

def test_strategy_prefers_the_priced_field_over_the_display_string():
    strategy = StrategyAgent()
    # A deliberately misleading display string: the number must win.
    priced = strategy._rate({"rate": "99% cash back", "valuePerDollar": 0.04}, "cashback")
    assert priced == 0.04


def test_strategy_still_reads_legacy_rules_without_the_priced_field():
    strategy = StrategyAgent()
    assert strategy._rate({"rate": "4% cash back"}, "cashback") == pytest.approx(0.04)


# -- html ------------------------------------------------------------------

def test_html_extraction_drops_scripts_and_styles():
    text = html_to_text("<html><head><style>.a{color:red}</style></head>"
                        "<body><script>var x=1</script><p>Earn 4% cash back</p></body></html>")
    assert "Earn 4% cash back" in text
    assert "color:red" not in text and "var x" not in text


# -- failure taxonomy -------------------------------------------------------

def test_no_terms_supplied_is_reported_as_such():
    agent = CardIntelligenceAgent(FakeRuntime())
    result = agent.parse({"name": "Card"})
    assert result["status"] == "failed"
    assert result["failureReason"] == "no_source"
    assert result["rules"] == []


def test_a_document_with_no_rates_fails_rather_than_guessing():
    agent = CardIntelligenceAgent(FakeRuntime(ExtractionResult(rules=[], confidence=0.0)))
    result = agent.parse({"name": "Card", "termsText": "Marketing copy with no rates."})
    assert result["status"] == "failed"
    assert result["failureReason"] == "no_rules_found"


def test_low_confidence_excludes_the_card():
    extraction = ExtractionResult(rules=[extracted()], confidence=0.1)
    agent = CardIntelligenceAgent(FakeRuntime(extraction))
    result = agent.parse({"name": "Card", "termsText": "Ambiguous copy."})
    assert result["status"] == "failed"
    assert result["failureReason"] == "low_confidence"
    assert result["rules"] == []


def test_a_transient_failure_keeps_existing_rules_and_goes_stale():
    """A rate limit must not throw away rules we already read successfully."""
    agent = CardIntelligenceAgent(FakeRuntime(error=ModelUnavailable("rate_limited", "quota")))
    previous = {"rules": [rule()], "confidence": 0.9, "source": {"label": "Issuer terms page",
                "locator": "https://issuer.example/rates", "retrievedAt": "2026-08-01"}}
    result = agent.parse({"name": "Card", "termsText": "..."}, previous)
    assert result["status"] == "stale"
    assert result["rules"] == previous["rules"]
    assert result["source"]["retrievedAt"] == "2026-08-01"


def test_a_transient_failure_with_nothing_on_file_fails_outright():
    agent = CardIntelligenceAgent(FakeRuntime(error=ModelUnavailable("rate_limited", "quota")))
    result = agent.parse({"name": "Card", "termsText": "..."}, None)
    assert result["status"] == "failed"


def test_a_document_with_no_rates_does_not_go_stale_even_with_history():
    """Reading successfully and finding nothing is a real answer, not an outage."""
    agent = CardIntelligenceAgent(FakeRuntime(ExtractionResult(rules=[], confidence=0.0)))
    previous = {"rules": [rule()], "confidence": 0.9, "source": {}}
    result = agent.parse({"name": "Card", "termsText": "..."}, previous)
    assert result["status"] == "failed"


# -- success shape ----------------------------------------------------------

def test_successful_extraction_prices_sorts_and_records_provenance():
    extraction = ExtractionResult(
        rules=[
            extracted(categoryLabel="Everything else", rateValue=0.3),
            extracted(categoryLabel="Dining", rateValue=5, cap=600, capType="spend", cycleLabel="per month"),
        ],
        confidence=0.9,
    )
    agent = CardIntelligenceAgent(FakeRuntime(extraction))
    result = agent.parse({"name": "Card", "termsText": "..."})

    assert result["status"] == "parsed"
    assert [r["categoryLabel"] for r in result["rules"]] == ["Dining", "Everything else"]
    assert result["rules"][0]["valuePerDollar"] == 0.05
    assert result["rules"][0]["rate"] == "5% cash back"
    assert result["rules"][0]["cap"] == 600.0
    assert result["source"]["locator"] == "pasted text"
    assert result["nextRecheckAt"] > result["source"]["retrievedAt"]
    assert all(rule["id"].startswith("rule-") for rule in result["rules"])


def test_rule_ids_are_stable_and_unique_for_duplicate_rules():
    rules = [rule(), rule(), rule(categoryLabel="Groceries")]

    first = with_rule_ids(rules)
    second = with_rule_ids(rules)

    assert [item["id"] for item in first] == [item["id"] for item in second]
    assert len({item["id"] for item in first}) == len(first)


# -- reward caps normalised to spend ---------------------------------------

def test_a_reward_cap_is_divided_back_through_the_rate():
    """"Up to $60 cashback a month" at 5% is $1,200 of spend, not $60."""
    from app.agents.schema import spend_cap
    assert spend_cap(rule(rateValue=5, rateUnit="percent", cap=60, capType="reward")) == 1200.0


def test_a_reward_cap_in_miles_converts_to_spend():
    # 3,600 miles at 4 miles per dollar is $900 of qualifying spend.
    from app.agents.schema import spend_cap
    priced = spend_cap(rule(rewardType="miles", rateValue=4, rateUnit="miles_per_dollar",
                            cap=3600, capType="reward"))
    assert priced == 900.0


def test_a_spend_cap_passes_through_untouched():
    from app.agents.schema import spend_cap
    assert spend_cap(rule(rateValue=5, rateUnit="percent", cap=600, capType="spend")) == 600.0


def test_strategy_allocates_against_the_spend_equivalent_cap():
    strategy = StrategyAgent()
    wallet = [{"cardId": "c1", "name": "Card", "last4": "1111", "parseStatus": "parsed",
               "track": "cashback", "accountId": "a1"}]
    rules = {"c1": [rule(categoryLabel="Dining", rateValue=5, rateUnit="percent",
                         cap=60, capType="reward", capSpend=1200.0, valuePerDollar=0.05,
                         cycleLabel="per month"),
                    rule(categoryLabel="Dining", rateValue=0.3, rateUnit="percent",
                         valuePerDollar=0.003)]}
    transactions = [{
        "category": "Dining", "amount": 2000, "accountId": "a1", "date": "2026-08-10",
    }]
    result = strategy.run(transactions, wallet, rules)
    # $1,200 earns 5% and the remaining $800 falls to 0.3%.
    assert result["categories"][0]["captured"] == pytest.approx(62.4, abs=0.01)
    assert result["categories"][0]["unclaimed"] == pytest.approx(0.0, abs=0.01)


def test_a_reward_cap_is_republished_as_spend_on_the_rule():
    """The interface renders `cap` as money, so it must always be spend."""
    extraction = ExtractionResult(
        rules=[extracted(categoryLabel="Dining", rewardType="miles", rateValue=4,
                    rateUnit="miles_per_dollar", cap=3600, capType="reward",
                    cycleLabel="per month")],
        confidence=0.9,
    )
    agent = CardIntelligenceAgent(FakeRuntime(extraction))
    parsed = agent.parse({"name": "Card", "termsText": "..."})["rules"][0]
    assert parsed["cap"] == 900.0
    assert parsed["capValue"] == 3600.0
    assert parsed["capType"] == "reward"


# -- per-programme valuation and currency ----------------------------------

def test_programmes_are_priced_individually_not_by_reward_type():
    """KrisFlyer miles and an unrecognised programme must not price the same."""
    from app.valuations import unit_value
    kris, _ = unit_value("KrisFlyer miles", "miles")
    amex, _ = unit_value("Membership Rewards", "points")
    unknown, _ = unit_value("Some Unlisted Programme", "miles")
    assert kris != unknown
    assert amex != kris
    assert kris > 0 and amex > 0


def test_programme_names_match_loosely():
    from app.valuations import unit_value
    exact, _ = unit_value("Reward points", "points")
    prefixed, _ = unit_value("HSBC Reward points", "points")
    assert exact == prefixed


def test_every_valuation_states_its_reasoning():
    """These are assumptions, so each must carry a source the UI can show."""
    from app.valuations import REWARD_UNIT_VALUES, DEFAULT_UNIT_VALUES
    for value, source in list(REWARD_UNIT_VALUES.values()) + list(DEFAULT_UNIT_VALUES.values()):
        assert value > 0
        assert source.strip()


def test_value_per_dollar_uses_the_named_programme():
    from app.valuations import unit_value
    kris, _ = unit_value("KrisFlyer miles", "miles")
    priced = value_per_dollar(
        rule(rewardType="miles", rateValue=1.2, rateUnit="miles_per_dollar"),
        "KrisFlyer miles",
    )
    assert priced == pytest.approx(1.2 * kris)


def test_cashback_is_never_repriced():
    assert value_per_dollar(rule(rateValue=5, rateUnit="percent"), "Anything") == 0.05


def test_extraction_records_currency_and_unit_price_on_every_rule():
    from app.agents.schema import ExtractedCharacteristics
    extraction = ExtractionResult(
        rules=[extracted(rewardType="miles", rateValue=1.2, rateUnit="miles_per_dollar")],
        characteristics=ExtractedCharacteristics(currency="SGD", rewardCurrency="KrisFlyer miles"),
        confidence=0.9,
    )
    parsed = CardIntelligenceAgent(FakeRuntime(extraction)).parse({"name": "C", "termsText": "..."})
    row = parsed["rules"][0]
    assert row["currency"] == "SGD"
    assert row["rewardCurrency"] == "KrisFlyer miles"
    assert row["rewardUnitValue"] > 0
    assert row["rewardUnitValueSource"]


def test_a_usd_card_keeps_its_own_currency():
    """A USD card is labelled, not silently converted at an invented rate."""
    from app.agents.schema import ExtractedCharacteristics
    extraction = ExtractionResult(
        rules=[extracted(rateValue=2, rateUnit="percent")],
        characteristics=ExtractedCharacteristics(currency="USD"),
        confidence=0.9,
    )
    parsed = CardIntelligenceAgent(FakeRuntime(extraction)).parse({"name": "C", "termsText": "..."})
    assert parsed["currency"] == "USD"
    assert parsed["rules"][0]["currency"] == "USD"


# -- complex reward structures ---------------------------------------------

def test_a_card_offering_a_choice_pays_in_the_holders_chosen_currency():
    """DBS yuu pays in yuu Points or cash back. The holder's track decides."""
    extraction = ExtractionResult(rules=[extracted(rewards=[
        {"rewardType": "cashback", "rateValue": 18, "rateUnit": "percent", "rewardCurrency": None},
        {"rewardType": "points", "rateValue": 18, "rateUnit": "points_per_dollar", "rewardCurrency": "yuu Points"},
    ])], confidence=0.9)

    cash = CardIntelligenceAgent(FakeRuntime(extraction)).parse(
        {"name": "yuu", "track": "cashback", "termsText": "..."})["rules"][0]
    points = CardIntelligenceAgent(FakeRuntime(extraction)).parse(
        {"name": "yuu", "track": "points", "termsText": "..."})["rules"][0]

    assert cash["rewardType"] == "cashback"
    assert points["rewardType"] == "points"
    assert cash["hasRewardChoice"] and points["hasRewardChoice"]
    # Each keeps the road not taken visible.
    assert cash["alternativeRewards"][0]["rewardType"] == "points"


def test_reward_options_that_price_far_apart_are_flagged():
    """Two ways of paying the same reward should not value 10x differently."""
    extraction = ExtractionResult(rules=[extracted(rewards=[
        {"rewardType": "cashback", "rateValue": 5, "rateUnit": "percent", "rewardCurrency": None},
        {"rewardType": "points", "rateValue": 50, "rateUnit": "points_per_dollar", "rewardCurrency": "Mystery Points"},
    ])], confidence=0.9)
    result = CardIntelligenceAgent(FakeRuntime(extraction)).parse({"name": "C", "termsText": "..."})
    assert any("price" in note for note in result["unresolved"])


def test_a_merchant_scoped_rate_says_so():
    """4% at three named shops is not 4% on a category."""
    extraction = ExtractionResult(rules=[extracted(
        merchants=["Cold Storage", "Giant", "Guardian"], minSpend=600,
    )], confidence=0.9)
    row = CardIntelligenceAgent(FakeRuntime(extraction)).parse({"name": "C", "termsText": "..."})["rules"][0]
    assert any("only at Cold Storage" in r for r in row["restrictions"])
    assert any("minimum spend" in r for r in row["restrictions"])


def test_a_nominated_category_rate_is_marked_conditional():
    extraction = ExtractionResult(rules=[extracted(
        requiresSelection=True, selectableCategories=["Dining", "Travel"],
        conditions=[{"kind": "banking_relationship", "description": "Requires a UOB One Account.",
                     "amount": None, "cycleLabel": "no cap"}],
    )], confidence=0.9)
    row = CardIntelligenceAgent(FakeRuntime(extraction)).parse({"name": "C", "termsText": "..."})["rules"][0]
    assert row["requiresSelection"] is True
    assert "you must nominate this category" in row["restrictions"]
    assert StrategyAgent().unmet_conditions(row) == ["Requires a UOB One Account."]


def test_unresolved_structures_are_reported_not_dropped():
    extraction = ExtractionResult(
        rules=[extracted()], confidence=0.9,
        unresolved=["Solitaire cardmembers may nominate two categories."],
    )
    result = CardIntelligenceAgent(FakeRuntime(extraction)).parse({"name": "C", "termsText": "..."})
    assert "Solitaire cardmembers may nominate two categories." in result["unresolved"]


# -- mcc matching -----------------------------------------------------------

def test_strategy_matches_on_mcc_before_label():
    """4121 is unambiguous; "Travel" and "Transport" are not."""
    strategy = StrategyAgent()
    transit = {"categoryLabel": "Rideshare", "mccCodes": ["4121"], "valuePerDollar": 0.04}
    assert strategy._matches(transit, "anything at all", mcc="4121")
    assert not strategy._matches(transit, "anything at all", mcc="5812")


def test_mcc_ranges_are_understood():
    strategy = StrategyAgent()
    air = {"categoryLabel": "Air travel", "mccCodes": ["3000-3299", "4511"]}
    assert strategy._matches(air, "", mcc="3100")
    assert strategy._matches(air, "", mcc="4511")
    assert not strategy._matches(air, "", mcc="5411")


def test_the_base_rate_matches_any_spending():
    strategy = StrategyAgent()
    base = {"categoryLabel": "Everything else", "mccCodes": []}
    assert strategy._matches(base, "groceries")
    assert strategy._matches(base, "anything")


def test_label_matching_still_works_without_codes():
    strategy = StrategyAgent()
    dining = {"categoryLabel": "Dining", "mccCodes": []}
    assert strategy._matches(dining, "Dining")
    assert not strategy._matches(dining, "Fuel")


# -- two-pass consolidation -------------------------------------------------

def test_a_condition_either_pass_found_survives_the_merge():
    """Misses between runs are uncorrelated, so the union is the honest view."""
    from app.agents.consolidate import consolidate
    first = ExtractionResult(rules=[extracted(
        conditions=[{"kind": "category_selection", "description": "Nominate one category.",
                     "amount": None, "count": None, "cycleLabel": "no cap"}])], confidence=0.9)
    second = ExtractionResult(rules=[extracted(
        conditions=[{"kind": "banking_relationship", "description": "Requires a One Account.",
                     "amount": None, "count": None, "cycleLabel": "no cap"}])], confidence=0.9)

    kinds = {c.kind for c in consolidate([first, second]).rules[0].conditions}
    assert kinds == {"category_selection", "banking_relationship"}


def test_scope_is_unioned_across_passes():
    from app.agents.consolidate import consolidate
    first = ExtractionResult(rules=[extracted(mccCodes=["5812"], merchants=["Giant"])], confidence=0.9)
    second = ExtractionResult(rules=[extracted(mccCodes=["5814"], merchants=["Cold Storage"])], confidence=0.9)
    merged = consolidate([first, second]).rules[0]
    assert set(merged.mccCodes) == {"5812", "5814"}
    assert set(merged.merchants) == {"Giant", "Cold Storage"}


def test_the_more_thorough_pass_is_the_base():
    from app.agents.consolidate import consolidate
    thin = ExtractionResult(rules=[extracted(categoryLabel="Dining")], confidence=0.9)
    thorough = ExtractionResult(rules=[extracted(categoryLabel="Dining"),
                                       extracted(categoryLabel="Everything else")], confidence=0.9)
    assert len(consolidate([thin, thorough]).rules) == 2


def test_a_rule_only_one_pass_saw_is_not_promoted():
    """Uncorroborated rules stay out; merging must not invent coverage."""
    from app.agents.consolidate import consolidate
    first = ExtractionResult(rules=[extracted(categoryLabel="Dining")], confidence=0.9)
    second = ExtractionResult(rules=[extracted(categoryLabel="Something Nobody Else Saw")], confidence=0.9)
    labels = {r.categoryLabel for r in consolidate([first, second]).rules}
    assert labels == {"Dining"}


def test_a_card_that_is_only_benefits_still_parses():
    """UOB One pays a fixed quarterly rebate and earns no percentage."""
    extraction = ExtractionResult(rules=[], confidence=0.9, benefits=[
        {"label": "Quarterly rebate", "kind": "statement_credit", "amount": 50,
         "cycleLabel": "per quarter", "conditions": [
             {"kind": "minimum_spend", "description": "Spend at least S$500 each month.",
              "amount": 500, "count": None, "cycleLabel": "per month"},
             {"kind": "transaction_count", "description": "At least 5 transactions each month.",
              "amount": None, "count": 5, "cycleLabel": "per month"}]},
    ])
    result = CardIntelligenceAgent(FakeRuntime(extraction)).parse({"name": "C", "termsText": "..."})
    assert result["status"] == "parsed"
    assert result["benefits"][0]["amount"] == 50


def test_a_card_with_neither_rules_nor_benefits_still_fails():
    extraction = ExtractionResult(rules=[], benefits=[], confidence=0.9)
    result = CardIntelligenceAgent(FakeRuntime(extraction)).parse({"name": "C", "termsText": "..."})
    assert result["status"] == "failed"
    assert result["failureReason"] == "no_rules_found"


# -- mcc backfill -----------------------------------------------------------

def test_missing_codes_are_filled_from_the_curated_map():
    from app.mcc import backfill
    rules = [{"categoryLabel": "Dining", "mccCodes": []}]
    filled, count = backfill(rules)
    assert count == 1
    assert "5812" in filled[0]["mccCodes"]
    assert filled[0]["mccSource"] == "inferred"


def test_codes_the_document_named_are_never_overwritten():
    from app.mcc import backfill
    rules = [{"categoryLabel": "Dining", "mccCodes": ["9999"]}]
    filled, count = backfill(rules)
    assert filled[0]["mccCodes"] == ["9999"]
    assert count == 0


def test_a_merchant_scoped_rule_gets_no_category_codes():
    """Giving a three-shop rate category codes would let it match far too much."""
    from app.mcc import backfill
    rules = [{"categoryLabel": "Groceries", "mccCodes": [], "merchants": ["Cold Storage"]}]
    filled, count = backfill(rules)
    assert filled[0]["mccCodes"] == []
    assert count == 0


def test_the_base_rate_gets_no_codes():
    from app.mcc import codes_for
    assert codes_for("Everything else") == []
    assert codes_for("All other spend") == []


def test_a_benefits_only_pass_is_not_discarded_when_merging():
    """UOB One earns no percentage; a pass that found only its rebate is real."""
    from app.agents.consolidate import consolidate
    benefits_only = ExtractionResult(rules=[], confidence=0.9, benefits=[
        {"label": "Quarterly rebate", "kind": "statement_credit", "amount": 50,
         "cycleLabel": "per quarter", "conditions": [
             {"kind": "minimum_spend", "description": "Spend S$500 monthly.",
              "amount": 500, "count": None, "cycleLabel": "per month"}]}])
    empty = ExtractionResult(rules=[], benefits=[], confidence=0.0)
    merged = consolidate([empty, benefits_only])
    assert merged.benefits and merged.confidence == 0.9
