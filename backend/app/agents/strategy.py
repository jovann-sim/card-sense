from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta


from .ingestion import is_eligible_purchase
from ..plaid_taxonomy import is_redirectable
from ..routing import options as routing_options, service as routing_service, verdict
from ..valuations import VALUATIONS  # noqa: F401  (re-exported; orchestrator imports it from here)

# Labels meaning "we could not place this", however they were produced.
UNCATEGORISED = {"uncategorised", "uncategorized", "unknown", ""}


def cap_cycle_kind(rule) -> str | None:
    """Normalise issuer/legacy cycle labels for cap accounting."""
    if not isinstance(rule, dict) or rule.get("capSpend", rule.get("cap")) is None:
        return None
    label = str(rule.get("cycleLabel") or "").strip().lower()
    if label in {"per month", "month", "monthly"}:
        return "month"
    if label in {"per quarter", "quarter", "quarterly"}:
        return "quarter"
    if label in {"per year", "year", "yearly", "annual", "annually"}:
        return "year"
    if label in {"per statement", "statement", "statement cycle", "per statement cycle"}:
        return "statement"
    return "unknown"


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
    # The transaction feed cannot prove that the holder enrolled, met a spend
    # threshold, made enough transactions, holds another banking product, or
    # falls inside a promotion. Until CardSense stores explicit eligibility
    # state, every extracted condition is blocking. Pricing it anyway turns a
    # possible return into money the dashboard claims was available.
    out = [
        condition.get("description") or condition.get("kind")
        for condition in rule.get("conditions") or []
        if isinstance(condition, dict)
    ]
    if rule.get("requiresSelection") and not out:
        out.append("This rate applies only to the category you nominate.")
    if rule.get("minSpend") is not None:
        out.append(f"This rate requires minimum spend of {float(rule['minSpend']):g} per cycle.")
    if rule.get("exclusions"):
        out.append("This rate has exclusions that cannot be verified from the transaction feed.")
    if cap_cycle_kind(rule) == "statement":
        out.append("This cap follows a statement cycle whose boundary is not available.")
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

    def run(self, transactions, wallet, rules, goal=None, *, routing=None):
        grouped = defaultdict(list)
        for tx in transactions:
            # A credit card bill payment or a transfer between your own
            # accounts is money moving, not money spent. Ingestion flags them;
            # counting them here would inflate every figure on the dashboard.
            if not is_eligible_purchase(tx):
                continue
            grouped[tx.get("category", "uncategorized")].append(tx)

        categories, total_captured, total_optimal, degraded = [], 0.0, 0.0, []
        routable: list[dict] = []
        chosen = routing_service(routing)
        optimal_cap_spend = defaultdict(float)
        captured_cap_spend = defaultdict(float)
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

            # A landlord does not take a Visa. Rent, tuition and most insurance
            # cannot go on a card at all, so pricing them at a card's rate
            # invents both the reward earned and the reward missed — and on a
            # real account rent is the largest line, which makes it the largest
            # fiction. They are held out of the comparison and answered
            # separately, by the only mechanism that applies: a bill-payment
            # service that charges a fee to do it for you.
            if is_redirectable(category, True):
                routable.append(self._routing_case(category, rows, spend, wallet, rules, chosen))
                continue

            # A display category can contain several MCCs, merchants and
            # payment channels. Keep those eligibility facts in the segment;
            # collapsing to MCC alone made merchant-only and online-only rates
            # look applicable to every purchase in the category.
            segments = {}
            for row in rows:
                key = (
                    str(row.get("mcc") or "") or None,
                    str(row.get("merchant") or "").strip().lower(),
                    str(row.get("paymentChannel") or "").strip().lower(),
                    str(row.get("currency") or "").strip().upper(),
                    bool(row.get("contactless", False)),
                    str(row.get("date") or "")[:10],
                )
                segment = segments.setdefault(key, {"amount": 0.0, "row": row})
                segment["amount"] += float(row.get("amount", 0))

            optimal = 0.0
            winner_value = defaultdict(float)
            for segment in segments.values():
                row = segment["row"]
                mcc = str(row.get("mcc") or "") or None
                segment_spend = segment["amount"]
                if segment_spend <= 0:
                    continue
                candidates = self._candidates(category, wallet, rules, mcc, row)
                value, allocations = self._allocate(
                    segment_spend, candidates, optimal_cap_spend, row,
                )
                optimal += value
                for rate, card, _rule, allocated in allocations:
                    winner_value[card["name"]] += allocated * rate

            best_name = max(winner_value, key=winner_value.get) if winner_value else None
            best = next((card for card in wallet if card.get("name") == best_name), None)
            best_value = winner_value.get(best_name, 0) if best_name else 0
            tied_names = [
                name for name, value in winner_value.items()
                if name != best_name and abs(value - best_value) < 0.0001
            ]

            captured = 0.0
            flags, used = (["ambiguous-merchant"] if any(row.get("categoryAmbiguous") for row in rows) else []), set()
            by_account = {card.get("accountId"): card for card in wallet if card.get("accountId")}
            for row in rows:
                card = by_account.get(row.get("accountId"))
                if not card:
                    flags.append("rules-unverified")
                    continue
                used.add(f"{card['name']} ••{card['last4']}")
                matched = self._candidates(category, [card], rules, row.get("mcc"), row)
                if not matched:
                    flags.append("rules-unverified")
                    degraded.append(
                        f"{category}: no verified rule on {card['name']} matched this transaction; "
                        "actual rewards exclude it."
                    )
                    continue
                value, _allocations = self._allocate(
                    float(row.get("amount", 0)), matched, captured_cap_spend, row,
                )
                captured += value
            if not used:
                degraded.append(f"{category}: no transaction is associated with a held card; actual rewards are unavailable.")
            total_captured += captured
            total_optimal += optimal
            item = {
                "mcc": ", ".join(sorted({str(row.get("mcc")) for row in rows if row.get("mcc")})) or "—",
                "category": category, "spend": round(spend, 2),
                "captured": round(captured, 2), "unclaimed": round(max(0, optimal - captured), 2),
                "usedCard": ", ".join(sorted(used)) or "Unassigned", "bestCard": best["name"] if best else "No verified card",
            }
            if "rules-unverified" in flags:
                item["note"] = (
                    "Actual rewards exclude transactions that are not mapped to a held card "
                    "or do not match a verified rule."
                )
            if flags:
                item["flags"] = sorted(set(flags))
            conditional = self._category_unmet_conditions(category, rows, wallet, rules)
            if conditional:
                item["flags"] = sorted(set([*item.get("flags", []), "conditional-rate"]))
                item["note"] = (item.get("note", "") + " " + conditional[0]).strip()
            if tied_names:
                item["note"] = (item.get("note", "") + " " + "Tied with " + ", ".join(tied_names) + ".").strip()
            categories.append(item)
        categories.sort(key=lambda item: item["unclaimed"], reverse=True)
        routable.sort(key=lambda item: item["spend"], reverse=True)
        return {"categories": categories, "routable": routable, "routingService": chosen.id,
                "captured": round(total_captured, 2), "unclaimed": round(max(0, total_optimal-total_captured), 2), "degraded": degraded}

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

    def _best_rate_for(self, category, rows, wallet, rules) -> tuple[float, str | None]:
        """The best rate any held card would pay, if this could go on one."""
        best, name = 0.0, None
        for row in rows:
            candidates = self._candidates(category, wallet, rules, row.get("mcc"), row)
            if candidates and candidates[0][0] > best:
                best, name = candidates[0][0], candidates[0][1]["name"]
        return best, name

    def _routing_case(self, category, rows, spend, wallet, rules, chosen) -> dict:
        """What a bill-payment service would actually do to this category.

        Reported whether or not it is a good idea. Staying silent on a losing
        trade would leave the user to assume rent is simply unrewardable, when
        the truth is that it is rewardable at a price which is usually too high
        — and occasionally, to reach a welcome bonus, is not.
        """
        rate, card = self._best_rate_for(category, rows, wallet, rules)
        priced = routing_options(spend, rate)
        mine = next((row for row in priced if row["service"] == chosen.id), priced[0] if priced else None)
        return {
            "category": category,
            "spend": round(spend, 2),
            "transactions": len(rows),
            "bestCard": card,
            "rewardRate": round(rate, 4),
            "service": chosen.id,
            "serviceName": chosen.name,
            "fee": mine["fee"] if mine else 0.0,
            "reward": mine["reward"] if mine else 0.0,
            "net": mine["net"] if mine else 0.0,
            "worthIt": bool(mine and mine["net"] > 0),
            "verdict": verdict(mine["net"] if mine else 0.0, category, chosen.name),
            "alternatives": priced,
        }

    def _candidates(self, category, wallet, rules, mcc=None, transaction=None):
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
                if not self._rule_is_eligible(rule, transaction, card):
                    continue
                candidates.append((rule_rate(rule, card.get("track")), card, rule))
        return sorted(candidates, key=lambda item: item[0], reverse=True)

    def _rule_is_eligible(self, rule, transaction, card) -> bool:
        """Only price a rate whose requirements the transaction can prove."""
        if unmet_rule_conditions(rule):
            return False

        row = transaction or {}
        if rule.get("capSpend", rule.get("cap")) is not None and self._cap_period(rule, row) is None:
            return False
        merchants = [str(value).strip().lower() for value in rule.get("merchants") or [] if value]
        if merchants:
            merchant = str(row.get("merchant") or "").strip().lower()
            if not merchant or not any(value in merchant or merchant in value for value in merchants):
                return False

        channels = {str(value).strip().lower().replace("-", "_").replace(" ", "_")
                    for value in rule.get("channels") or [] if value}
        channels.discard("any")
        if channels and not self._channel_matches(channels, row, card):
            return False
        return True

    def _channel_matches(self, channels, transaction, card) -> bool:
        supplied = str(transaction.get("paymentChannel") or "").strip().lower().replace("-", "_").replace(" ", "_")
        if "online" in channels and supplied == "online":
            return True
        if "in_store" in channels and supplied in {"in_store", "in_person"}:
            return True
        if "contactless" in channels and (
            transaction.get("contactless") is True or supplied == "contactless"
        ):
            return True
        if "foreign_currency" in channels:
            transaction_currency = str(transaction.get("currency") or "").upper()
            card_currency = str(card.get("currency") or "").upper()
            if transaction_currency and card_currency and transaction_currency != card_currency:
                return True
        return False

    def _allocate(self, amount, candidates, cap_spend, transaction=None):
        """Price spend through verified cap headroom and return its allocation."""
        if not candidates or amount == 0:
            return 0.0, []
        if amount < 0:
            rate, card, rule = candidates[0]
            key = self._cap_key(card, rule, transaction)
            if rule.get("capSpend", rule.get("cap")) is not None:
                cap_spend[key] = max(0.0, cap_spend[key] + amount)
            return amount * rate, [(rate, card, rule, amount)]

        remaining, value, allocations = amount, 0.0, []
        for rate, card, rule in candidates:
            cap = rule.get("capSpend", rule.get("cap"))
            key = self._cap_key(card, rule, transaction)
            headroom = remaining if cap is None else max(0.0, float(cap) - cap_spend[key])
            allocated = min(remaining, headroom)
            if allocated <= 0:
                continue
            value += allocated * rate
            cap_spend[key] += allocated
            allocations.append((rate, card, rule, allocated))
            remaining -= allocated
            if remaining <= 0:
                break
        return value, allocations

    def _cap_key(self, card, rule, transaction=None):
        return (
            card.get("cardId") or card.get("name"),
            rule.get("capGroup") or rule.get("id") or rule.get("categoryLabel"),
            rule.get("cycleLabel", ""),
            self._cap_period(rule, transaction or {}),
        )

    def _cap_period(self, rule, transaction) -> str | None:
        """Calendar bucket in which this rule's spend cap is consumed."""
        if rule.get("capSpend", rule.get("cap")) is None:
            return "uncapped"
        kind = cap_cycle_kind(rule)
        if kind in {"statement", "unknown"}:
            return None
        try:
            when = date.fromisoformat(str(transaction.get("date") or "")[:10])
        except (TypeError, ValueError):
            return None
        if kind == "month":
            return f"{when.year:04d}-{when.month:02d}"
        if kind == "quarter":
            return f"{when.year:04d}-Q{((when.month - 1) // 3) + 1}"
        if kind == "year":
            return f"{when.year:04d}"
        return None

    def _category_unmet_conditions(self, category, rows, wallet, rules):
        """Explain higher rates that were excluded instead of pricing them."""
        reasons = []
        for card in wallet:
            if card.get("parseStatus") != "parsed":
                continue
            for rule in rules.get(card.get("cardId"), []):
                if not any(rule_matches(rule, category, row.get("mcc")) for row in rows):
                    continue
                for reason in unmet_rule_conditions(rule):
                    if reason not in reasons:
                        reasons.append(reason)
                if (
                    rule.get("capSpend", rule.get("cap")) is not None
                    and any(self._cap_period(rule, row) is None for row in rows)
                    and cap_cycle_kind(rule) != "statement"
                ):
                    reason = "This cap has no supported cycle or transaction date, so its remaining headroom is unverified."
                    if reason not in reasons:
                        reasons.append(reason)
        return reasons

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
