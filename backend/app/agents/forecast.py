from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from math import sqrt
from statistics import pstdev

from .ingestion import is_eligible_purchase
from .strategy import rule_matches, rule_rate, unmet_rule_conditions


class ForecastAgent:
    """Deterministic near-term spend projection and dated cap warnings."""

    id = "forecast"
    horizon_days = 30
    history_limit_days = 90

    def run(
        self,
        transactions,
        planned,
        wallet=None,
        rules=None,
        *,
        today: date | None = None,
        leakage_rate: float = 0.0,
    ) -> dict:
        as_of = today or date.today()
        eligible = self._dated_transactions(transactions, as_of)
        recent = [row for row in eligible if row["parsedDate"] >= as_of - timedelta(days=89)]

        if recent:
            first = min(row["parsedDate"] for row in recent)
            history_days = (as_of - first).days + 1
            daily = defaultdict(float)
            for row in recent:
                daily[row["parsedDate"]] += float(row["transaction"].get("amount", 0))
            samples = [daily[first + timedelta(days=offset)] for offset in range(history_days)]
            baseline = max(0.0, sum(samples) / history_days * self.horizon_days)
            observed_band = 1.28 * pstdev(samples) * sqrt(self.horizon_days) if len(samples) > 1 else 0.0
            floor = baseline * (0.30 if history_days < 14 else 0.10)
            confidence = max(observed_band, floor)
            quality = "limited" if history_days < 14 else "good"
        else:
            history_days, baseline, confidence, quality = 0, 0.0, 0.0, "none"

        in_window = self._planned_in_window(planned, as_of)
        planned_spend = sum(float(item.get("amount", 0)) for item in in_window)
        projected = max(0.0, baseline + planned_spend)
        leakage_rate = min(1.0, max(0.0, float(leakage_rate or 0)))

        timeline = self.timeline(
            in_window,
            transactions,
            wallet or [],
            rules or {},
        )
        return {
            "horizonDays": self.horizon_days,
            "baselineSpend": round(baseline, 2),
            "plannedSpend": round(planned_spend, 2),
            "projectedSpend": round(projected, 2),
            "historyDays": history_days,
            "quality": quality,
            "confidence": round(confidence, 2),
            "basis": self._basis(history_days, bool(in_window)),
            "timeline": timeline,
            "doNothingCost": round(projected * leakage_rate, 2),
            "doNothingWindow": f"over the next {self.horizon_days} days",
        }

    def degraded(self, forecast: dict) -> list[str]:
        if forecast["quality"] == "none":
            return ["No eligible recent transactions were available; the projection contains declared spending only."]
        if forecast["quality"] == "limited":
            return [f"Only {forecast['historyDays']} days of recent history were available, so the range is deliberately wide."]
        return []

    def timeline(self, planned, transactions=None, wallet=None, rules=None):
        transactions, wallet, rules = transactions or [], wallet or [], rules or {}
        entries: list[dict] = []
        allocated = defaultdict(float)
        for item in sorted(planned, key=lambda row: (str(row.get("startDate", "")), str(row.get("id", "")))):
            when = self._parse_date(item.get("startDate"))
            if when is None:
                continue
            entries.append({
                "date": str(when),
                "kind": item["kind"],
                "title": item["label"],
                "detail": item.get("note") or "You declared this.",
                "amount": float(item["amount"]),
            })
            collision = self._cap_collision(item, when, transactions, wallet, rules, allocated)
            if collision:
                entries.append(collision)
        return sorted(entries, key=lambda item: (item["date"], 0 if item["kind"] in {"event", "purchase"} else 1))

    def project_cards(self, transactions, wallet, rules, *, today: date | None = None) -> list[dict]:
        as_of = today or date.today()
        cards = []
        for card in wallet:
            card_rules = rules.get(card.get("cardId"), [])
            first = card_rules[0] if card_rules else {}
            cap = first.get("capSpend", first.get("cap")) if first else None
            cycle = self._cycle_bounds(first.get("cycleLabel"), as_of) if cap is not None else None
            note = card.get("parseNote")
            state, used = "healthy", 0.0
            if card.get("parseStatus") != "parsed":
                state = "unverified"
            elif cap is not None and cycle is None:
                state = "unverified"
                note = note or "Statement-cycle cap usage cannot be projected without a statement boundary."
            elif cap is not None:
                used = self._used_spend(card, first, transactions, cycle[0], as_of)
                ratio = used / float(cap) if float(cap) > 0 else 1.0
                state = "reached" if ratio >= 1 else ("approaching" if ratio >= 0.8 else "healthy")
            cards.append({
                "name": card["name"],
                "last4": card["last4"],
                "network": card["network"],
                "categoryLabel": first.get("categoryLabel", "Unverified"),
                "rate": first.get("rate", "—"),
                "cycleSpend": round(used, 2),
                "cap": float(cap) if cap is not None else None,
                "cycleLabel": first.get("cycleLabel", "no cap"),
                "state": state,
                **({"note": note} if note else {}),
            })
        return cards

    def _cap_collision(self, item, when, transactions, wallet, rules, allocated):
        categories = item.get("categories") or []
        category = categories[0] if categories else ""
        candidates = self._forecast_candidates(category, wallet, rules)
        if not candidates:
            return None
        _rate, card, rule = candidates[0]
        cap = rule.get("capSpend", rule.get("cap"))
        cycle = self._cycle_bounds(rule.get("cycleLabel"), when) if cap is not None else None
        if cap is None or cycle is None:
            return None

        cap_key = (
            card.get("cardId"),
            rule.get("capGroup") or rule.get("id") or rule.get("categoryLabel"),
            str(cycle[0]),
        )
        used = self._used_spend(card, rule, transactions, cycle[0], when) + allocated[cap_key]
        amount = float(item.get("amount", 0))
        headroom = max(0.0, float(cap) - used)
        allocated[cap_key] += min(amount, headroom)
        if amount <= headroom:
            return None

        alternative = next((candidate for candidate in candidates[1:] if candidate[1].get("cardId") != card.get("cardId")), None)
        if alternative:
            alternative_name = alternative[1]["name"]
            action = (
                f"Split it — {headroom:,.2f} on {card['name']} ••{card['last4']}, "
                f"then use {alternative_name}."
                if headroom > 0 else
                f"That cap is already used. Put this on {alternative_name} instead."
            )
        else:
            action = (
                f"Use only {headroom:,.2f} on {card['name']} before switching to a verified uncapped card."
                if headroom > 0 else
                "Use a verified uncapped card instead."
            )
        return {
            "date": str(when),
            "kind": "cap",
            "title": f"{category} passes {card['name']}'s cap",
            "detail": (
                f"{used:,.2f} of the {float(cap):,.2f} {rule.get('cycleLabel', 'cycle')} cap "
                f"is already allocated; this plan exceeds it by {max(0.0, amount - headroom):,.2f}."
            ),
            "action": action,
        }

    def _forecast_candidates(self, category, wallet, rules):
        candidates = []
        for card in wallet:
            if card.get("parseStatus") != "parsed":
                continue
            for rule in rules.get(card.get("cardId"), []):
                if not rule_matches(rule, category):
                    continue
                # A plan supplies a category, date and amount—not merchant,
                # channel, enrolment or relationship state. Do not recommend a
                # rate whose eligibility cannot be established from that input.
                if (unmet_rule_conditions(rule) or rule.get("minSpend") or rule.get("merchants")
                        or rule.get("channels") or rule.get("exclusions")):
                    continue
                candidates.append((rule_rate(rule, card.get("track")), card, rule))
        return sorted(candidates, key=lambda candidate: candidate[0], reverse=True)

    def _used_spend(self, card, rule, transactions, start: date, end: date) -> float:
        account_id = card.get("accountId")
        if not account_id:
            return 0.0
        total = 0.0
        for transaction in transactions:
            when = self._parse_date(transaction.get("date"))
            if (not when or when < start or when > end or not is_eligible_purchase(transaction)
                    or transaction.get("accountId") != account_id):
                continue
            if rule_matches(rule, transaction.get("category"), transaction.get("mcc")):
                total += float(transaction.get("amount", 0))
        return max(0.0, total)

    def _dated_transactions(self, transactions, as_of: date):
        rows = []
        for transaction in transactions:
            when = self._parse_date(transaction.get("date"))
            if when and when <= as_of and is_eligible_purchase(transaction):
                rows.append({"parsedDate": when, "transaction": transaction})
        return rows

    def _planned_in_window(self, planned, as_of: date):
        end = as_of + timedelta(days=self.horizon_days - 1)
        return [item for item in planned if (when := self._parse_date(item.get("startDate"))) and as_of <= when <= end]

    def _cycle_bounds(self, label, when: date):
        value = str(label or "").lower()
        if value in {"per month", "month", "monthly"}:
            return when.replace(day=1), when
        if value in {"per quarter", "quarter", "quarterly"}:
            month = ((when.month - 1) // 3) * 3 + 1
            return when.replace(month=month, day=1), when
        if value in {"per year", "year", "yearly", "annual"}:
            return when.replace(month=1, day=1), when
        return None

    def _parse_date(self, value) -> date | None:
        try:
            return date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            return None

    def _basis(self, history_days: int, has_plans: bool) -> str:
        if history_days == 0:
            history = "No recent transaction history was available"
        elif history_days < 14:
            history = f"Only {history_days} days of transaction history were available, so the range is conservative"
        else:
            history = f"Based on {history_days} days of transaction history and observed daily variability"
        plans = "; declared spending is included at the entered amount" if has_plans else ""
        return f"{history}{plans}. Not seasonality."
