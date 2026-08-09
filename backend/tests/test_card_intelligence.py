from __future__ import annotations

import pytest

from app.agents.card_intelligence import CardIntelligenceAgent
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
    base = {
        "categoryLabel": "Dining", "rewardType": "cashback", "rateValue": 4.0,
        "rateUnit": "percent", "cap": None, "capType": None,
        "cycleLabel": "no cap", "minSpend": None, "notes": None,
    }
    return {**base, **kwargs}


# -- pricing ----------------------------------------------------------------

def test_percentage_prices_as_a_fraction_of_the_dollar():
    assert value_per_dollar(rule(rateValue=4, rateUnit="percent")) == 0.04


def test_miles_price_through_the_reward_currency():
    # 1.4 miles per dollar at $0.013 a mile returns $0.0182 per dollar spent.
    priced = value_per_dollar(rule(rewardType="miles", rateValue=1.4, rateUnit="miles_per_dollar"))
    assert priced == pytest.approx(0.0182)


def test_points_price_through_the_reward_currency():
    priced = value_per_dollar(rule(rewardType="points", rateValue=10, rateUnit="points_per_dollar"))
    assert priced == pytest.approx(0.1)


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
    extraction = ExtractionResult(rules=[rule()], confidence=0.1)
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
            rule(categoryLabel="Everything else", rateValue=0.3),
            rule(categoryLabel="Dining", rateValue=5, cap=600, capType="spend", cycleLabel="per month"),
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
                         cap=60, capType="reward", capSpend=1200.0, valuePerDollar=0.05),
                    rule(categoryLabel="Dining", rateValue=0.3, rateUnit="percent",
                         valuePerDollar=0.003)]}
    transactions = [{"category": "Dining", "amount": 2000, "accountId": "a1"}]
    result = strategy.run(transactions, wallet, rules)
    # $1,200 earns 5% and the remaining $800 falls to 0.3%.
    assert result["categories"][0]["captured"] == pytest.approx(100.0, abs=0.01)


def test_a_reward_cap_is_republished_as_spend_on_the_rule():
    """The interface renders `cap` as money, so it must always be spend."""
    extraction = ExtractionResult(
        rules=[rule(categoryLabel="Dining", rewardType="miles", rateValue=4,
                    rateUnit="miles_per_dollar", cap=3600, capType="reward",
                    cycleLabel="per month")],
        confidence=0.9,
    )
    agent = CardIntelligenceAgent(FakeRuntime(extraction))
    parsed = agent.parse({"name": "Card", "termsText": "..."})["rules"][0]
    assert parsed["cap"] == 900.0
    assert parsed["capValue"] == 3600.0
    assert parsed["capType"] == "reward"
