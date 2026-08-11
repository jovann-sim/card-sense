"""Adversarial input for the ingestion agent.

A bank feed is not a clean dataset. Fields go missing, amounts arrive as
strings, categories are unrecognised, refunds are negative, and the same
transaction is re-sent as an update. None of that should crash a pipeline whose
output every other agent depends on, and none of it should silently corrupt a
figure the user reads as money.
"""

from __future__ import annotations

import pytest

from app.agents.ingestion import IngestionAgent, is_eligible_purchase
from app.agents.strategy import StrategyAgent
from app.orchestrator import transaction_totals
from app.plaid_taxonomy import classify


agent = IngestionAgent()


# -- malformed input --------------------------------------------------------

def test_a_transaction_with_no_fields_at_all_does_not_crash():
    row = agent.normalise_plaid({})
    assert row["amount"] == 0
    assert row["merchant"] == "Unknown"
    assert row["mcc"] is None


@pytest.mark.parametrize("pfc", [None, "", [], "FOOD_AND_DRINK", {"primary": None}])
def test_a_malformed_category_block_is_survivable(pfc):
    """Plaid's category has arrived as a string and as null in the wild."""
    row = agent.normalise_plaid({"transaction_id": "t", "amount": 10, "personal_finance_category": pfc})
    assert row["category"]
    assert isinstance(row["isPurchase"], bool)


def test_an_unrecognised_category_is_uncategorised_not_a_guess():
    mcc, label, purchase = classify("SOMETHING_PLAID_ADDED_LAST_WEEK", "AND_A_NEW_DETAIL")
    assert mcc is None
    assert label == "Uncategorised"
    assert purchase is True


def test_an_amount_arriving_as_a_string_does_not_poison_the_totals():
    row = agent.normalise_plaid({"transaction_id": "t", "amount": "42.50"})
    assert row["amount"] == 42.5


# -- refunds and signs ------------------------------------------------------

def test_a_refund_reduces_spend_rather_than_adding_to_it():
    rows = [
        agent.normalise_plaid({"transaction_id": "a", "amount": 100.0}),
        agent.normalise_plaid({"transaction_id": "b", "amount": -30.0}),
    ]
    totals = transaction_totals(rows)
    assert totals["spend"] == 100.0
    assert totals["refunds"] == 30.0
    assert totals["netSpend"] == 70.0


def test_a_refund_is_marked_as_one():
    assert agent.normalise_plaid({"transaction_id": "r", "amount": -12.0})["isRefund"] is True


# -- what must never reach the reward maths ---------------------------------

@pytest.mark.parametrize("primary", ["TRANSFER_IN", "TRANSFER_OUT", "LOAN_PAYMENTS", "BANK_FEES", "INCOME"])
def test_money_moving_is_never_a_purchase(primary):
    row = agent.normalise_plaid({
        "transaction_id": "t", "amount": 5000.0,
        "personal_finance_category": {"primary": primary, "detailed": f"{primary}_OTHER"},
    })
    assert row["isPurchase"] is False
    assert is_eligible_purchase(row) is False


def test_a_pending_transaction_is_not_counted_until_it_posts():
    """A pending charge can change amount or vanish; counting it invents money."""
    row = agent.normalise_plaid({"transaction_id": "t", "amount": 80.0, "pending": True})
    assert is_eligible_purchase(row) is False


def test_uncategorised_spending_never_reaches_the_comparison():
    """Crediting it at the base rate would add the same figure to both sides."""
    txs = [
        {"category": "Dining", "amount": 100, "isPurchase": True, "mcc": "5812"},
        {"category": "Uncategorised", "amount": 9000, "isPurchase": True},
    ]
    result = StrategyAgent().run(txs, [], {})
    assert [c["category"] for c in result["categories"]] == ["Dining"]


# -- scale and idempotence --------------------------------------------------

def test_a_large_feed_is_summarised_without_choking():
    rows = [agent.normalise_plaid({
        "transaction_id": f"t{i}", "amount": 10.0,
        "personal_finance_category": {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_RESTAURANT"},
    }) for i in range(5000)]
    summary = agent.summarise(rows)
    assert summary["purchases"] == 5000
    assert summary["mccCoverage"] == 1.0


def test_normalising_the_same_transaction_twice_gives_the_same_row():
    """Plaid re-sends a transaction as `modified`; the result must not drift."""
    tx = {"transaction_id": "t", "amount": 10.0, "merchant_category_code": "5812",
          "personal_finance_category": {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_RESTAURANT"}}
    first, second = agent.normalise_plaid(tx), agent.normalise_plaid(tx)
    ignore = {"updatedAt"}
    assert {k: v for k, v in first.items() if k not in ignore} == \
           {k: v for k, v in second.items() if k not in ignore}


def test_an_empty_feed_reports_zero_rather_than_dividing_by_it():
    summary = agent.summarise([])
    assert summary["purchases"] == 0
    assert summary["mccCoverage"] == 0.0
    assert agent.degraded(summary) == []


# -- coverage reporting -----------------------------------------------------

def test_a_feed_with_poor_mcc_coverage_says_so():
    rows = [{"isPurchase": True, "mcc": None, "accountId": "a"} for _ in range(10)]
    assert agent.degraded(agent.summarise(rows, linked_account_ids={"a"}))


def test_transactions_on_an_unlinked_account_are_reported():
    rows = [{"isPurchase": True, "mcc": "5812", "accountId": "unknown-account"}]
    notes = agent.degraded(agent.summarise(rows, linked_account_ids={"linked"}))
    assert any("not linked" in note for note in notes)


# -- webhook ---------------------------------------------------------------

def test_a_non_transaction_webhook_is_acknowledged_not_acted_on():
    from app import main
    result = main.plaid_webhook({"webhook_type": "ITEM", "webhook_code": "ERROR"})
    assert result["ok"] is True and result["handled"] is False


def test_an_unknown_transaction_code_is_acknowledged():
    """Acknowledging stops Plaid retrying something we will never handle."""
    from app import main
    result = main.plaid_webhook({"webhook_type": "TRANSACTIONS", "webhook_code": "SOMETHING_NEW"})
    assert result["ok"] is True and result["handled"] is False


def test_an_empty_webhook_body_does_not_crash():
    from app import main
    assert main.plaid_webhook({})["ok"] is True


def test_a_sync_webhook_without_plaid_configured_is_declined_cleanly(monkeypatch):
    from app import main
    monkeypatch.setattr(type(main.settings), "use_plaid", property(lambda self: False))
    result = main.plaid_webhook({"webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE"})
    assert result["handled"] is False and "not configured" in result["reason"]


# -- engine parity ----------------------------------------------------------

def test_the_run_endpoint_accepts_an_engine():
    """Both engines write the same read model, so the choice is not observable."""
    from app.models import RunIn
    assert RunIn().engine is None
    assert RunIn(engine="adk").engine == "adk"
    assert RunIn(engine="orchestrator").engine == "orchestrator"


def test_an_unknown_engine_is_rejected():
    import pydantic
    from app.models import RunIn
    with pytest.raises(pydantic.ValidationError):
        RunIn(engine="something-else")


def test_the_orchestrator_remains_the_default():
    """The graph is proven against the orchestrator, not trusted over it."""
    from app.config import settings
    assert settings.pipeline_engine == "orchestrator"


def test_every_graph_node_maps_to_a_read_model_agent():
    """An unmapped node would run but never appear on the activity page."""
    from adk_agents.pipeline.runner import NODE_TO_AGENT
    from app.orchestrator import AGENTS

    known = {ident for ident, _label in AGENTS}
    assert set(NODE_TO_AGENT.values()) == known


def test_the_graph_covers_every_agent_in_the_architecture():
    from adk_agents.pipeline.agent import build_pipeline
    from app.orchestrator import AGENTS

    pipeline = build_pipeline("demo-user", "test-run")
    names = set()
    for edge in pipeline.edges:
        for node in edge:
            if not isinstance(node, str):
                names.add(node.name)
    assert len(names) == len(AGENTS), f"graph has {names}"
