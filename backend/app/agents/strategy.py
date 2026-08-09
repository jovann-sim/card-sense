from __future__ import annotations
from collections import defaultdict

class StrategyAgent:
    id="strategy"
    def run(self, summary, wallet, rules, goal=None):
        categories=[]
        total_captured=0.0; total_optimal=0.0
        for category, spend in summary["categories"].items():
            candidates=[]
            for card in wallet:
                if card.get("parseStatus") == "failed": continue
                for rule in rules.get(card["name"],[]):
                    label=rule.get("categoryLabel","").lower()
                    if category.lower() in label or label in category.lower():
                        rate=self._rate(rule.get("rate"), card.get("track"))
                        candidates.append((rate,card))
            base=0.01
            captured=spend*base
            best=max(candidates,key=lambda x:x[0],default=(base,None))
            optimal=spend*best[0]
            total_captured += captured; total_optimal += optimal
            categories.append({"mcc":"—","category":category,"spend":round(spend,2),"captured":round(captured,2),"unclaimed":round(max(0,optimal-captured),2),"usedCard":"Current wallet","bestCard":best[1]["name"] if best[1] else "Current wallet"})
        categories.sort(key=lambda x:x["unclaimed"],reverse=True)
        return {"categories":categories,"captured":round(total_captured,2),"unclaimed":round(max(0,total_optimal-total_captured),2)}
    def _rate(self, raw, track):
        s=str(raw).lower().replace("%","")
        import re
        m=re.search(r"(\d+(?:\.\d+)?)",s)
        if not m:return .01
        v=float(m.group(1))
        return v/100 if "%" in str(raw) else v*.01
