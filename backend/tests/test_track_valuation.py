"""The reward-track comparison used to be a tautology: nominal was set to the
same captured dollar figure for every track, so cashback/miles/points always
showed one identical number despite claiming to compare three different
outcomes. These prove the three tracks now come from genuinely different
optimisations, each priced through that reward family's own real cards.
"""
from app.orchestrator import Orchestrator
from app.agents.strategy import StrategyAgent, VALUATIONS


def _orchestrator():
    # _track_valuation only touches self.strategy; bypass __init__ so the test
    # needs no store, no Firestore, no Gemini runtime.
    orch = Orchestrator.__new__(Orchestrator)
    orch.strategy = StrategyAgent()
    return orch


def _tx(category, mcc, amount, account, tid):
    return {"id": tid, "date": "2026-08-01", "merchant": category, "amount": amount,
            "category": category, "mcc": mcc, "isPurchase": True, "accountId": account}


WALLET = [
    {"cardId": "cash", "name": "Flat Cashback", "last4": "1111", "network": "Visa",
     "track": "cashback", "accountId": "a", "parseStatus": "parsed"},
    {"cardId": "pts", "name": "Points Card", "last4": "2222", "network": "Amex",
     "track": "points", "accountId": "b", "parseStatus": "parsed"},
]
RULES = {
    "cash": [{"id": "c", "categoryLabel": "Everything else", "rate": "2%", "valuePerDollar": 0.02, "mccCodes": []}],
    "pts": [{"id": "p", "categoryLabel": "Everything else", "rate": "5x",
             "valuePerDollar": 5 * 0.021, "mccCodes": []}],  # real Amex MR rate
}
# A miles card the user does not hold, so only the catalog counterfactual can
# reach it.
CATALOG = [{
    "id": "miles-card", "name": "Miles Explorer", "network": "Visa", "track": "miles",
    "annualFee": 0,
    "rules": [{"id": "m", "categoryLabel": "Everything else", "rate": "3x",
               "valuePerDollar": 3 * 0.013, "mccCodes": []}],
}]


def test_the_three_tracks_are_no_longer_identical():
    orch = _orchestrator()
    transactions = [_tx("Dining", "5812", 1000.0, "a", "t1")]

    rows = [
        orch._track_valuation(name, value, 999.0, transactions, WALLET, RULES, CATALOG)
        for name, value in VALUATIONS.items()
    ]
    nominals = {row["track"]: row["nominal"] for row in rows}

    assert len(set(nominals.values())) == 3, f"tracks were not distinct: {nominals}"


def test_each_track_reflects_its_own_best_card():
    orch = _orchestrator()
    transactions = [_tx("Dining", "5812", 1000.0, "a", "t1")]

    cashback = orch._track_valuation("cashback", VALUATIONS["cashback"], 999.0,
                                     transactions, WALLET, RULES, CATALOG)
    points = orch._track_valuation("points", VALUATIONS["points"], 999.0,
                                   transactions, WALLET, RULES, CATALOG)
    miles = orch._track_valuation("miles", VALUATIONS["miles"], 999.0,
                                  transactions, WALLET, RULES, CATALOG)

    assert cashback["nominal"] == 20.0                      # 2% of $1,000
    assert points["nominal"] == round(1000 * 5 * 0.021, 2)  # held Amex-rate card
    assert miles["nominal"] == round(1000 * 3 * 0.013, 2)   # catalog-only card
    assert not cashback["isPlaceholder"]
    assert not points["isPlaceholder"]
    assert not miles["isPlaceholder"]


def test_a_track_with_no_matching_card_falls_back_to_the_placeholder():
    """No held or catalogued card belongs to this track — nothing to optimise
    against, so the old generic-rate assumption is the only honest answer."""
    orch = _orchestrator()
    transactions = [_tx("Dining", "5812", 1000.0, "a", "t1")]
    wallet = [WALLET[0]]  # cashback only
    rules = {"cash": RULES["cash"]}

    miles = orch._track_valuation("miles", VALUATIONS["miles"], 500.0,
                                  transactions, wallet, rules, [])

    assert miles["isPlaceholder"] is True
    assert miles["nominal"] == 500.0  # falls back to the passed-in captured figure


def test_a_catalog_card_already_held_is_not_double_counted():
    """If the held card and a catalog row share a name, only the held one
    (with its real accountId and attribution) should be optimised against."""
    orch = _orchestrator()
    transactions = [_tx("Dining", "5812", 1000.0, "a", "t1")]
    catalog_with_duplicate = CATALOG + [{
        "id": "dup", "name": "Points Card", "network": "Amex", "track": "points",
        "annualFee": 0, "rules": [{"id": "d", "categoryLabel": "Everything else",
                                   "rate": "10x", "valuePerDollar": 10 * 0.021, "mccCodes": []}],
    }]

    points = orch._track_valuation("points", VALUATIONS["points"], 999.0,
                                   transactions, WALLET, RULES, catalog_with_duplicate)

    # The 10x duplicate must not be picked up — only the real 5x held card.
    assert points["nominal"] == round(1000 * 5 * 0.021, 2)
