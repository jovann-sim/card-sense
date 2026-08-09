from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta


VALUATIONS = {"cashback": 1.0, "points": 0.01, "miles": 0.013}


class StrategyAgent:
    id = "strategy"

    def run(self, transactions, wallet, rules, goal=None):
        grouped = defaultdict(list)
        for tx in transactions:
            grouped[tx.get("category", "uncategorized")].append(tx)

        categories, total_captured, total_optimal, degraded = [], 0.0, 0.0, []
        cap_spend = defaultdict(float)
        for category, rows in grouped.items():
            spend = sum(float(row.get("amount", 0)) for row in rows)
            candidates = self._candidates(category, wallet, rules)
            optimal_rate = candidates[0][0] if candidates else 0.0
            tied = [card for rate, card, _ in candidates if abs(rate - optimal_rate) < 0.0001]
            best = tied[0] if tied else None
            optimal = 0.0
            # Allocate category spend through cap headroom, then to the next rate.
            remaining = spend
            for rate, card, rule in candidates:
                # capSpend normalises a reward cap ("up to $60 cashback") into
                # the spend that reaches it, which is what is being allocated.
                cap = rule.get("capSpend", rule.get("cap")) if isinstance(rule, dict) else None
                headroom = remaining if cap is None else max(0.0, float(cap) - cap_spend[(card["name"], rule.get("cycleLabel", ""))])
                allocated = min(remaining, headroom)
                optimal += allocated * rate
                cap_spend[(card["name"], rule.get("cycleLabel", ""))] += allocated
                remaining -= allocated
                if remaining <= 0:
                    break
            if remaining:
                optimal += remaining * 0.01

            captured = 0.0
            flags, used = (["ambiguous-merchant"] if any(row.get("categoryAmbiguous") for row in rows) else []), set()
            by_account = {card.get("accountId"): card for card in wallet if card.get("accountId")}
            for row in rows:
                card = by_account.get(row.get("accountId"))
                if not card:
                    flags.append("rules-unverified")
                    continue
                used.add(f"{card['name']} ••{card['last4']}")
                matched = self._candidates(category, [card], rules)
                captured += float(row.get("amount", 0)) * (matched[0][0] if matched else 0.01)
            if not used:
                degraded.append(f"{category}: no transaction is associated with a held card; actual rewards are unavailable.")
            total_captured += captured
            total_optimal += optimal
            item = {
                "mcc": "—", "category": category, "spend": round(spend, 2),
                "captured": round(captured, 2), "unclaimed": round(max(0, optimal - captured), 2),
                "usedCard": ", ".join(sorted(used)) or "Unassigned", "bestCard": best["name"] if best else "No verified card",
            }
            if flags:
                item["flags"] = sorted(set(flags))
                item["note"] = "Actual rewards exclude transactions not mapped to a held card."
            if len(tied) > 1:
                item["note"] = (item.get("note", "") + " " + "Tied with " + ", ".join(c["name"] for c in tied[1:]) + ".").strip()
            categories.append(item)
        categories.sort(key=lambda item: item["unclaimed"], reverse=True)
        return {"categories": categories, "captured": round(total_captured, 2), "unclaimed": round(max(0, total_optimal-total_captured), 2), "degraded": degraded}

    def goal_projection(self, goal, captured):
        if not goal:
            return None
        rate = VALUATIONS[goal["track"]]
        pace = captured / rate if rate else 0
        projected = None
        if goal.get("target") is not None and pace > 0:
            months = max(0, (goal["target"] - goal.get("current", 0)) / pace)
            projected = str(date.today() + timedelta(days=round(months * 30)))
        out = {**goal, "pacePerMonth": round(pace, 2), "projectedAt": projected}
        if projected and goal.get("deadline") and projected > str(goal["deadline"]):
            out["fix"] = {"action": "Route eligible spending to the highest-value verified card.", "pacePerMonth": round(pace * 1.1, 2), "projectedAt": str(date.today() + timedelta(days=round(max(0, months * 30 / 1.1))))}
        return out

    def _candidates(self, category, wallet, rules):
        candidates = []
        for card in wallet:
            if card.get("parseStatus") != "parsed":
                continue
            for rule in rules.get(card.get("cardId"), []):
                label = rule.get("categoryLabel", "").lower()
                if category.lower() in label or label in category.lower():
                    candidates.append((self._rate(rule, card.get("track")), card, rule))
        return sorted(candidates, key=lambda item: item[0], reverse=True)

    def _rate(self, rule, track):
        """Nominal dollars returned per dollar spent.

        Card intelligence now supplies this directly as valuePerDollar, priced
        through the reward currency at extraction time. The regex below is a
        fallback for rules recorded before that field existed — it reads a
        display string like "4% cash back", which is guesswork by comparison.
        """
        if isinstance(rule, dict) and rule.get("valuePerDollar") is not None:
            return float(rule["valuePerDollar"])

        raw = rule.get("rate") if isinstance(rule, dict) else rule
        match = re.search(r"(\d+(?:\.\d+)?)", str(raw))
        if not match:
            return 0.01
        value = float(match.group(1))
        return (value / 100 if "%" in str(raw) else value * 0.01) * VALUATIONS.get(track, 1)
