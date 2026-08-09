from app.agents.strategy import StrategyAgent

def test_strategy_never_negative_gap():
    s={"categories":{"Dining":100},"spend":100,"monthly":{}}
    wallet=[{"name":"Dining Card","track":"cashback","parseStatus":"parsed"}]
    rules={"Dining Card":[{"categoryLabel":"Dining","rate":"4%"}]}
    out=StrategyAgent().run(s,wallet,rules)
    assert out["captured"] >= 0
    assert out["unclaimed"] >= 0
