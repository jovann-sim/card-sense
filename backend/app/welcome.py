from __future__ import annotations

from datetime import date, timedelta

from .agents.ingestion import is_eligible_purchase
from .routing import bonus_case, service as routing_service
from .valuations import VALUATIONS

# Spending that issuers almost universally refuse to count toward a minimum.
# Counting it would tell someone they had qualified when the issuer disagrees,
# which is the one error in this feature that costs real money.
NEVER_QUALIFIES = {"Transfers & payments"}


def _parse(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def bonus_value(bonus: dict, track: str | None = None) -> float:
    """The award in dollars, priced through the same table as everything else."""
    unit = str(bonus.get("unit") or track or "points").lower()
    rate = VALUATIONS.get(unit, VALUATIONS.get("points", 0.01))
    return round(float(bonus.get("award") or 0) * rate, 2)


def qualifying_spend(transactions, account_id, start: date, end: date) -> tuple[float, int]:
    """Spend on this card, inside the window, that the issuer would count."""
    total, count = 0.0, 0
    for row in transactions:
        if not is_eligible_purchase(row) or row.get("accountId") != account_id:
            continue
        when = _parse(row.get("date"))
        if not when or when < start or when > end:
            continue
        if row.get("category") in NEVER_QUALIFIES:
            continue
        amount = float(row.get("amount") or 0)
        if amount <= 0:          # a refund reduces qualifying spend, as issuers do
            total += amount
            continue
        total += amount
        count += 1
    return round(max(0.0, total), 2), count


def track_held(card: dict, bonus: dict, transactions, *, today: date | None = None) -> dict | None:
    """Progress toward a bonus on a card already held.

    Returns None when the card has no opening date, because without one the
    window is unknowable and a guessed deadline is worse than no deadline.
    """
    as_of = today or date.today()
    opened = _parse(card.get("openedAt"))
    if opened is None:
        return None

    window = int(bonus.get("windowDays") or 90)
    deadline = opened + timedelta(days=window)
    minimum = float(bonus.get("minSpend") or 0)
    earned, count = qualifying_spend(transactions, card.get("accountId"), opened, min(as_of, deadline))
    gap = max(0.0, minimum - earned)
    days_left = (deadline - as_of).days
    value = bonus_value(bonus, card.get("track"))

    # Pace is only meaningful while the window is open and the target unmet.
    needed_per_day = gap / days_left if gap > 0 and days_left > 0 else 0.0
    elapsed = max(1, (min(as_of, deadline) - opened).days)
    current_per_day = earned / elapsed

    if gap <= 0:
        state = "met"
    elif days_left <= 0:
        state = "missed"
    elif current_per_day * days_left >= gap:
        state = "on-track"
    else:
        state = "at-risk"

    return {
        "cardId": card.get("cardId"),
        "card": card.get("name"),
        "state": state,
        "award": float(bonus.get("award") or 0),
        "unit": bonus.get("unit") or card.get("track") or "points",
        "valueUsd": value,
        "minSpend": minimum,
        "qualifyingSpend": earned,
        "transactions": count,
        "gap": round(gap, 2),
        "openedAt": str(opened),
        "deadline": str(deadline),
        "daysLeft": days_left,
        "perDayNeeded": round(needed_per_day, 2),
        "perDayCurrent": round(current_per_day, 2),
        "excludes": bonus.get("excludes") or [],
    }


def rescue(progress: dict, service_id: str | None = None) -> dict | None:
    """Whether paying a fee to route bills would save an at-risk bonus.

    This is the one case where a bill-payment service is worth its fee. Routing
    rent for two percent back is a losing trade every time; routing it to close
    the last eight hundred dollars of a four-thousand-dollar minimum buys a six
    hundred dollar award for twenty-three dollars, and that is simply a good
    trade with an unfamiliar shape.
    """
    if progress["state"] not in {"at-risk", "on-track"} or progress["gap"] <= 0:
        return None
    chosen = routing_service(service_id)
    case = bonus_case(progress["gap"], progress["valueUsd"], chosen.feeRate)
    if not case:
        return None
    return {**case, "service": chosen.id, "serviceName": chosen.name, "feeRate": chosen.feeRate}


def qualify_catalog(card: dict, bonus: dict, monthly_spend: float, *, today: date | None = None) -> dict:
    """Whether the user's own spending would clear a bonus they have not started.

    The question a catalog page should answer is not "what does this card pay"
    but "would I actually get the headline number". Someone spending nine
    hundred a month will not reach a four-thousand minimum in three months, and
    the card is worth less to them than the advertisement implies.
    """
    window = int(bonus.get("windowDays") or 90)
    minimum = float(bonus.get("minSpend") or 0)
    months = window / 30.44
    projected = monthly_spend * months
    value = bonus_value(bonus, card.get("track"))

    shortfall = max(0.0, minimum - projected)
    return {
        "card": card.get("name"),
        "award": float(bonus.get("award") or 0),
        "unit": bonus.get("unit") or "points",
        "valueUsd": value,
        "minSpend": minimum,
        "windowDays": window,
        "projectedSpend": round(projected, 2),
        "monthlySpend": round(monthly_spend, 2),
        "qualifies": shortfall <= 0,
        "shortfall": round(shortfall, 2),
        # How long the minimum actually takes at this rate, which is the number
        # that decides whether the window is generous or the card is unsuitable.
        "monthsToMinimum": round(minimum / monthly_spend, 1) if monthly_spend > 0 else None,
        "monthsAllowed": round(months, 1),
    }
