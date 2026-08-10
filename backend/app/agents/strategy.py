from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta


from .ingestion import is_eligible_purchase
from ..valuations import VALUATIONS

# Labels meaning "we could not place this", however they were produced.
UNCATEGORISED = {"uncategorised", "uncategorized", "unknown", ""}  # noqa: F401  (re-exported; orchestrator imports it from here)


def mcc_in(mcc: str, codes: list[str]) -> bool:
    """Whether an MCC appears in a list of individual codes or ranges."""
    for code in codes:
        code = str(code).strip()
        if "-" in code:
            low, _, high = code.partition("-")
            if low.strip().isdigit() and high.strip().isdigit() and mcc.isdigit():
                if int(low) <= int(mcc) <= int(high):
                    return True
        elif code == mcc:
            return True
    return False


def rule_matches(rule, category, mcc=None) -> bool:
    codes = rule.get("mccCodes") or [] if isinstance(rule, dict) else []
    if mcc and codes:
        return mcc_in(str(mcc), codes)

    label = (rule.get("categoryLabel") or "").lower()
    if label in {"everything else", "all other spend", "base"}:
        return True
    category = (category or "").lower()
    return bool(category) and (category in label or label in category)


def unmet_rule_conditions(rule) -> list[str]:
    if not isinstance(rule, dict):
        return []
    blocking = {"category_selection", "banking_relationship", "enrolment", "new_customer"}
    out = [condition.get("description") or condition.get("kind") for condition in rule.get("conditions") or []
           if condition.get("kind") in blocking]
    if rule.get("requiresSelection") and not out:
        out.append("This rate applies only to the category you nominate.")
    return out


def rule_rate(rule, track) -> float:
    if isinstance(rule, dict) and rule.get("valuePerDollar") is not None:
        return float(rule["valuePerDollar"])

    raw = rule.get("rate") if isinstance(rule, dict) else rule
    match = re.search(r"(\d+(?:\.\d+)?)", str(raw))
    if not match:
        return 0.01
    value = float(match.group(1))
    return (value / 100 if "%" in str(raw) else value * 0.01) * VALUATIONS.get(track, 1)


class StrategyAgent:
    id = "strategy"

    def run(self, transactions, wallet, rules, goal=None):
        grouped = defaultdict(list)
        for tx in transactions:
            # A credit card bill payment or a transfer between your own
            # accounts is money moving, not money spent. Ingestion flags them;
            # counting them here would inflate every figure on the dashboard.
            if not is_eligible_purchase(tx):
                continue
            grouped[tx.get("category", "uncategorized")].append(tx)

        categories, total_captured, total_optimal, degraded = [], 0.0, 0.0, []
        cap_spend = defaultdict(float)
        for category, rows in grouped.items():
            spend = sum(float(row.get("amount", 0)) for row in rows)
            if spend <= 0:
                continue

            # Spending we could not categorise is left out of the comparison
            # entirely, on both sides. Crediting it at the base rate would add
            # the same figure to captured and to optimal, which understates the
            # gap as a proportion and makes a cashback percentage read lower
            # than the card actually pays. It still counts as spend — it was
            # spent — it simply cannot be optimised, and the interface says so.
            if not category or str(category).lower() in UNCATEGORISED:
                continue

            # A display category can contain several different MCCs. Price
            # each net MCC bucket separately; using the first row's code for
            # the whole category made a hotel purchase look like a flight.
            segments = defaultdict(float)
            for row in rows:
                segments[str(row.get("mcc") or "") or None] += float(row.get("amount", 0))

            optimal = 0.0
            winner_value = defaultdict(float)
            representative_rule = None
            tied_names: list[str] = []
            for mcc, segment_spend in segments.items():
                if segment_spend <= 0:
                    continue
                candidates = self._candidates(category, wallet, rules, mcc)
                if candidates:
                    top_rate = candidates[0][0]
                    segment_ties = [card for rate, card, _ in candidates if abs(rate - top_rate) < 0.0001]
                    for card in segment_ties:
                        if card["name"] not in tied_names:
                            tied_names.append(card["name"])
                    winner_value[candidates[0][1]["name"]] += segment_spend * top_rate
                    representative_rule = representative_rule or candidates[0][2]

                # Allocate this MCC's spend through cap headroom, then to the
                # next applicable rule/card.
                remaining = segment_spend
                for rate, card, rule in candidates:
                    cap = rule.get("capSpend", rule.get("cap")) if isinstance(rule, dict) else None
                    cap_key = (card["name"], rule.get("capGroup") or rule.get("id") or rule.get("categoryLabel"),
                               rule.get("cycleLabel", ""))
                    headroom = remaining if cap is None else max(0.0, float(cap) - cap_spend[cap_key])
                    allocated = min(remaining, headroom)
                    optimal += allocated * rate
                    cap_spend[cap_key] += allocated
                    remaining -= allocated
                    if remaining <= 0:
                        break
                if remaining:
                    optimal += remaining * 0.01

            best_name = max(winner_value, key=winner_value.get) if winner_value else None
            best = next((card for card in wallet if card.get("name") == best_name), None)

            captured = 0.0
            flags, used = (["ambiguous-merchant"] if any(row.get("categoryAmbiguous") for row in rows) else []), set()
            by_account = {card.get("accountId"): card for card in wallet if card.get("accountId")}
            for row in rows:
                card = by_account.get(row.get("accountId"))
                if not card:
                    flags.append("rules-unverified")
                    continue
                used.add(f"{card['name']} ••{card['last4']}")
                matched = self._candidates(category, [card], rules, row.get("mcc"))
                captured += float(row.get("amount", 0)) * (matched[0][0] if matched else 0.01)
            if not used:
                degraded.append(f"{category}: no transaction is associated with a held card; actual rewards are unavailable.")
            total_captured += captured
            total_optimal += optimal
            item = {
                "mcc": ", ".join(sorted(mcc for mcc in segments if mcc)) or "—",
                "category": category, "spend": round(spend, 2),
                "captured": round(captured, 2), "unclaimed": round(max(0, optimal - captured), 2),
                "usedCard": ", ".join(sorted(used)) or "Unassigned", "bestCard": best["name"] if best else "No verified card",
            }
            if flags:
                item["flags"] = sorted(set(flags))
                item["note"] = "Actual rewards exclude transactions not mapped to a held card."
            conditional = self.unmet_conditions(representative_rule)
            if conditional:
                item["flags"] = sorted(set([*item.get("flags", []), "conditional-rate"]))
                item["note"] = (item.get("note", "") + " " + conditional[0]).strip()
            other_ties = [name for name in tied_names if name != best_name]
            if other_ties:
                item["note"] = (item.get("note", "") + " " + "Tied with " + ", ".join(other_ties) + ".").strip()
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

    def _candidates(self, category, wallet, rules, mcc=None):
        """Rules that could pay for this spending, best first.

        Matching prefers the merchant category code, because a label match is
        guesswork: "Travel" and "Transport" read alike and mean different
        things, while 4121 is unambiguous.
        """
        candidates = []
        for card in wallet:
            if card.get("parseStatus") != "parsed":
                continue
            for rule in rules.get(card.get("cardId"), []):
                if not rule_matches(rule, category, mcc):
                    continue
                candidates.append((rule_rate(rule, card.get("track")), card, rule))
        return sorted(candidates, key=lambda item: item[0], reverse=True)

    def _matches(self, rule, category, mcc=None):
        return rule_matches(rule, category, mcc)

    def _mcc_in(self, mcc: str, codes: list[str]) -> bool:
        return mcc_in(mcc, codes)

    def unmet_conditions(self, rule) -> list[str]:
        """Qualifiers we cannot verify from transactions alone.

        Recorded so a rate that depends on nominating a category or holding a
        savings account is presented as conditional rather than counted as if
        the user had already done it.
        """
        return unmet_rule_conditions(rule)

    def _rate(self, rule, track):
        """Nominal dollars returned per dollar spent.

        Card intelligence now supplies this directly as valuePerDollar, priced
        through the reward currency at extraction time. The regex below is a
        fallback for rules recorded before that field existed — it reads a
        display string like "4% cash back", which is guesswork by comparison.
        """
        return rule_rate(rule, track)
