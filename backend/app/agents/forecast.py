from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from math import sqrt
from statistics import pstdev

from .ingestion import is_eligible_purchase
from .recurring import detect_streams, occurrences_between, split_history
from .strategy import rule_matches, rule_rate, unmet_rule_conditions

DAYS_PER_MONTH = 30.44


def add_months(start: date, months: int) -> date:
    """The same day-of-month, `months` later, clamped to the month's length.

    Calendar arithmetic rather than 30-day blocks: over a twelve-month horizon
    the difference is five days, which is a whole rent payment.
    """
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


class ForecastAgent:
    """Deterministic spend projection over a chosen horizon, and dated cap warnings.

    Three sources feed it, and they are kept apart because they behave
    differently. Recurring commitments repeat on a schedule and are projected by
    date. Variable spending is a daily rate measured on what is left after the
    commitments are removed. Declared plans are taken at the entered amount and
    never averaged, because the user knows about them and the history does not.
    """

    id = "forecast"
    horizon_days = 30
    history_limit_days = 90
    horizon_presets = (1, 3, 6, 12)

    def run(
        self,
        transactions,
        planned,
        wallet=None,
        rules=None,
        *,
        today: date | None = None,
        leakage_rate: float = 0.0,
        horizon_months: int = 1,
    ) -> dict:
        as_of = today or date.today()
        months = self._clamp_months(horizon_months)
        end = add_months(as_of, months) - timedelta(days=1)
        horizon_days = (end - as_of).days + 1

        # Streams are detected on everything available, because a quarterly bill
        # needs more than a quarter of history to be visible at all.
        streams = detect_streams(transactions, today=as_of)

        window_start = as_of - timedelta(days=self.history_limit_days - 1)
        recent = [
            row for row in self._dated_transactions(transactions, as_of)
            if row["parsedDate"] >= window_start
        ]
        _committed, variable_rows = split_history(
            [row["transaction"] for row in recent], streams, today=as_of
        )

        history_days, daily_mean, daily_sd = self._daily_rate(variable_rows, as_of)
        variable = max(0.0, daily_mean * horizon_days)
        recurring = self._recurring_spend(streams, as_of, end)
        baseline = variable + recurring

        in_window = self._planned_in_window(planned, as_of, end)
        planned_spend = sum(float(item.get("amount", 0)) for item in in_window)
        projected = max(0.0, baseline + planned_spend)

        confidence = self._band(
            self._variable_sd(daily_sd, horizon_days, history_days, variable),
            self._recurring_sd(streams, as_of, end, months),
        )
        quality = "none" if history_days == 0 else ("limited" if history_days < 14 else "good")
        reliable = self._reliable_months(history_days)
        leakage_rate = min(1.0, max(0.0, float(leakage_rate or 0)))

        return {
            "horizonDays": horizon_days,
            "horizonMonths": months,
            # Kept as history-derived spend so baseline + planned = projected
            # still holds for anything reading the older shape.
            "baselineSpend": round(baseline, 2),
            "variableSpend": round(variable, 2),
            "recurringSpend": round(recurring, 2),
            "plannedSpend": round(planned_spend, 2),
            "projectedSpend": round(projected, 2),
            "historyDays": history_days,
            "quality": quality,
            "confidence": round(confidence, 2),
            "reliableMonths": reliable,
            "extrapolated": months > reliable,
            "basis": self._basis(history_days, bool(in_window), months, reliable, streams),
            "months": self._monthly(as_of, months, daily_mean, daily_sd, history_days, streams, planned),
            "categories": self._categories(
                variable_rows, history_days, horizon_days, streams, in_window, as_of, end, projected
            ),
            "recurring": [
                {key: stream[key] for key in (
                    "merchant", "category", "cadence", "amount", "monthlyAmount",
                    "occurrences", "nextDue", "confidence",
                )}
                for stream in streams
            ],
            "timeline": self.timeline(in_window, transactions, wallet or [], rules or {}),
            "doNothingCost": round(projected * leakage_rate, 2),
            "doNothingWindow": self._window_phrase(months),
        }

    def degraded(self, forecast: dict) -> list[str]:
        notes = []
        if forecast["quality"] == "none":
            notes.append("No eligible recent transactions were available; the projection contains declared spending only.")
        elif forecast["quality"] == "limited":
            notes.append(f"Only {forecast['historyDays']} days of recent history were available, so the range is deliberately wide.")
        if forecast.get("extrapolated"):
            notes.append(
                f"{forecast['historyDays']} days of history supports roughly {forecast['reliableMonths']} "
                f"months of projection; the {forecast['horizonMonths']}-month figure is an extrapolation "
                "and its range is wide enough to say so."
            )
        return notes

    # -- projection --------------------------------------------------------

    def _clamp_months(self, months) -> int:
        try:
            value = int(months)
        except (TypeError, ValueError):
            return 1
        return min(12, max(1, value))

    def _daily_rate(self, rows, as_of: date) -> tuple[int, float, float]:
        """Mean and spread of daily variable spend, over the observed span.

        Days with no spending are real zeros and stay in the sample — dropping
        them would price a week of spending as if it happened every day.
        """
        dated = [(when, row) for row in rows if (when := self._parse_date(row.get("date")))]
        if not dated:
            return 0, 0.0, 0.0
        first = min(when for when, _ in dated)
        history_days = (as_of - first).days + 1
        daily = defaultdict(float)
        for when, row in dated:
            daily[when] += float(row.get("amount", 0))
        samples = [daily[first + timedelta(days=offset)] for offset in range(history_days)]
        return history_days, sum(samples) / history_days, pstdev(samples) if len(samples) > 1 else 0.0

    # How wrong a detected stream's projected total can be, before the horizon
    # is taken into account. Two charges is one interval of evidence; three
    # regular charges at a stable amount is a great deal more.
    STREAM_ERROR = {"high": 0.05, "medium": 0.12, "low": 0.25}

    # Added per month, for the chance a commitment lapses or reprices. A year
    # is long enough to move house, switch phone plans and cancel a gym.
    STREAM_DRIFT_PER_MONTH = 0.02

    def _variable_sd(self, daily_sd: float, horizon_days: int, history_days: int, variable: float) -> float:
        """Uncertainty in the variable half, as a standard deviation.

        Two errors compound. Day-to-day variation grows with the square root of
        the horizon, which is the familiar term. But the daily mean was itself
        estimated from a finite history, and that error grows *linearly* with
        the horizon — so projecting a year from a month is wrong in a way that
        projecting a month from a month is not. Adding both variances gives
        sd = σ·√(t + t²/n), and it is the second term that dominates far out.
        """
        if history_days == 0:
            return 0.0
        observed = daily_sd * sqrt(horizon_days + horizon_days ** 2 / history_days)
        floor = variable * (0.30 if history_days < 14 else 0.10) / 1.28
        return max(observed, floor)

    def _recurring_sd(self, streams, start: date, end: date, months: int) -> float:
        """Uncertainty in the committed half, which is not zero.

        Treating a detected commitment as certain is what made an early version
        of this claim a range of half a percent on a twelve-month projection —
        more confident than the naive forecaster it replaced, and wrong. A
        stream can be a false positive, its amount can move, and the longer the
        horizon the likelier it simply stops.

        Streams are combined in quadrature, which assumes they fail
        independently. They do not entirely — moving house changes the rent and
        the utilities together — so this is the optimistic end of honest.
        """
        variance = 0.0
        for stream in streams:
            projected = len(occurrences_between(stream, start, end)) * float(stream["amount"])
            if projected <= 0:
                continue
            relative = (
                self.STREAM_ERROR.get(stream.get("confidence"), 0.25)
                + self.STREAM_DRIFT_PER_MONTH * months
            )
            variance += (projected * relative) ** 2
        return sqrt(variance)

    def _band(self, variable_sd: float, recurring_sd: float) -> float:
        """An 80% range over both halves of the projection."""
        return 1.28 * sqrt(variable_sd ** 2 + recurring_sd ** 2)

    def _reliable_months(self, history_days: int) -> int:
        """How far out the history genuinely supports projecting.

        Three times the observed span, which is a rule of thumb rather than a
        theorem — but stating one at all is the point. It is what lets the
        interface distinguish a forecast from an extrapolation.
        """
        if history_days == 0:
            return 0
        return min(12, max(1, round(history_days * 3 / DAYS_PER_MONTH)))

    def _recurring_spend(self, streams, start: date, end: date) -> float:
        return sum(
            len(occurrences_between(stream, start, end)) * float(stream["amount"])
            for stream in streams
        )

    def _monthly(self, as_of, months, daily_mean, daily_sd, history_days, streams, planned) -> list[dict]:
        """Month-by-month buckets, with a cumulative range on each.

        The range is cumulative rather than per-month because that is the
        question people actually ask — not "what will March cost" but "where
        will I be by March".
        """
        buckets = []
        cumulative = 0.0
        for index in range(months):
            start = as_of if index == 0 else add_months(as_of, index)
            finish = add_months(as_of, index + 1) - timedelta(days=1)
            days = (finish - start).days + 1
            if days <= 0:
                continue

            variable = max(0.0, daily_mean * days)
            recurring = self._recurring_spend(streams, start, finish)
            declared = sum(
                float(item.get("amount", 0)) for item in planned
                if (when := self._parse_date(item.get("startDate"))) and start <= when <= finish
            )
            total = variable + recurring + declared
            cumulative += total
            elapsed = (finish - as_of).days
            buckets.append({
                "month": f"{finish.year:04d}-{finish.month:02d}",
                "label": finish.strftime("%b %Y"),
                "days": days,
                "variable": round(variable, 2),
                "recurring": round(recurring, 2),
                "planned": round(declared, 2),
                "total": round(total, 2),
                "cumulative": round(cumulative, 2),
                "cumulativeConfidence": round(
                    self._band(
                        self._variable_sd(daily_sd, elapsed, history_days, daily_mean * elapsed),
                        self._recurring_sd(streams, as_of, finish, index + 1),
                    ), 2
                ),
            })
        return buckets

    def _categories(self, variable_rows, history_days, horizon_days, streams,
                    planned, as_of: date, end: date, projected: float) -> list[dict]:
        """Where the projected money goes, which is what the strategy agent needs.

        A total tells you how much you will spend. A breakdown tells you which
        card should carry it, and that is the only version of this figure the
        rest of the system can act on.
        """
        variable = defaultdict(float)
        codes = defaultdict(set)
        for row in variable_rows:
            label = row.get("category") or "Uncategorised"
            variable[label] += float(row.get("amount", 0))
            if row.get("mcc"):
                codes[label].add(str(row["mcc"]))

        scale = horizon_days / history_days if history_days else 0.0
        combined = {label: amount * scale for label, amount in variable.items()}

        recurring = defaultdict(float)
        for stream in streams:
            label = stream.get("category") or "Uncategorised"
            recurring[label] += len(occurrences_between(stream, as_of, end)) * float(stream["amount"])
            if stream.get("mcc"):
                codes[label].add(str(stream["mcc"]))

        # A holiday tagged with flights, hotels and dining is spread across all
        # three. The cap warnings deliberately pick one card instead, because
        # "where does the money go" and "which limit does it breach" are
        # different questions.
        declared = defaultdict(float)
        for item in planned:
            labels = [label for label in (item.get("categories") or []) if label] or ["Planned"]
            share = float(item.get("amount", 0)) / len(labels)
            for label in labels:
                declared[label] += share

        rows = []
        for label in set(combined) | set(recurring) | set(declared):
            total = combined.get(label, 0.0) + recurring.get(label, 0.0) + declared.get(label, 0.0)
            if total <= 0:
                continue
            rows.append({
                "category": label,
                "mcc": ", ".join(sorted(codes.get(label, ()))) or "—",
                "variable": round(combined.get(label, 0.0), 2),
                "recurring": round(recurring.get(label, 0.0), 2),
                "planned": round(declared.get(label, 0.0), 2),
                "projected": round(total, 2),
                "monthly": round(total / horizon_days * DAYS_PER_MONTH, 2) if horizon_days else 0.0,
                "share": round(total / projected, 4) if projected > 0 else 0.0,
            })
        return sorted(rows, key=lambda row: row["projected"], reverse=True)

    def _window_phrase(self, months: int) -> str:
        if months == 1:
            return "over the next month"
        return f"over the next {months} months"

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

    def _planned_in_window(self, planned, as_of: date, end: date | None = None):
        finish = end or as_of + timedelta(days=self.horizon_days - 1)
        return [item for item in planned if (when := self._parse_date(item.get("startDate"))) and as_of <= when <= finish]

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

    def _basis(self, history_days: int, has_plans: bool, months: int = 1,
               reliable: int = 0, streams=None) -> str:
        if history_days == 0:
            history = "No recent transaction history was available"
        elif history_days < 14:
            history = f"Only {history_days} days of transaction history were available, so the range is conservative"
        else:
            history = f"Based on {history_days} days of transaction history and observed daily variability"

        parts = [history]
        if streams:
            parts.append(
                f"{len(streams)} recurring commitment{'s' if len(streams) != 1 else ''} "
                "projected by billing date rather than averaged"
            )
        if has_plans:
            parts.append("declared spending included at the entered amount")
        if months > reliable:
            parts.append(f"months {reliable + 1}-{months} are extrapolated beyond the history")

        # Naming what this is not matters as much as naming what it is: nobody
        # should read a twelve-month figure as if it knew about Christmas.
        return "; ".join(parts) + ". Not seasonality."
