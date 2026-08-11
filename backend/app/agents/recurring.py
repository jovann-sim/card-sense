from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from statistics import median

from .ingestion import is_eligible_purchase

# Cadence buckets, by the gap in days between charges.
#
# Real billing dates drift: a monthly subscription lands on the 28th of
# February and the 31st of March, and a weekly one slips a day when the
# processor's batch runs late. Each bucket is therefore a range, and the last
# column is how many times it charges in an average month — which is what turns
# a stream into a monthly commitment.
CADENCES: list[tuple[str, int, int, float]] = [
    ("weekly", 6, 8, 52 / 12),
    ("fortnightly", 12, 15, 26 / 12),
    # Twice a month, not every fourteen days: paid on the 1st and the 15th, the
    # gaps alternate 14 and 17 and average slightly over a fortnight.
    ("semi-monthly", 16, 18, 2.0),
    ("monthly", 26, 34, 1.0),
    ("quarterly", 84, 96, 1 / 3),
    ("yearly", 350, 380, 1 / 12),
]

# How far past its due date a stream can drift before we stop projecting it.
# A cancelled subscription must not be forecast for another eleven months.
LAPSE_FACTOR = 1.8

# Categories where a merchant legitimately charges you on a schedule.
#
# From transactions alone, "KFC, $500, every thirty days, three times running"
# is arithmetically identical to a subscription — same merchant, same gap, same
# amount. The only thing separating them is what the merchant *is*. A landlord
# and a gym bill monthly by arrangement; a fried chicken shop does not, and a
# repeating charge there is a habit that happens to be regular.
#
# The distinction is not cosmetic. A commitment is projected on its billing
# date and carries little uncertainty. A habit is real spending, but claiming
# to know its date and amount is a certainty we have not earned — so it goes
# back into the variable pool, where it still counts, priced as a rate with a
# range around it.
BILL_CATEGORIES = {
    "Rent", "Utilities", "Insurance", "Streaming", "Fitness", "Education",
    "Medical", "Services", "Government", "Telecom", "Personal care",
}


def is_billable(category: str | None) -> bool:
    return (category or "") in BILL_CATEGORIES

_NOISE = re.compile(r"[^a-z0-9 ]+")
# The display form keeps the issuer's own casing, so its noise pattern has to
# spare capitals — stripping them turned "United Airlines" into "nited irlines".
_NOISE_ANY_CASE = re.compile(r"[^A-Za-z0-9 ]+")
_HAS_DIGIT = re.compile(r"\d")


def normalise_merchant(name: str | None) -> str:
    """A merchant key that survives store numbers and transaction references.

    "STARBUCKS #1147" and "STARBUCKS #0392" are the same subscription-shaped
    habit; "NETFLIX 8H2KQ" and "NETFLIX 4B1XZ" are the same subscription. Tokens
    containing digits are almost always the part that varies, so they go — but
    only if something survives, because dropping them from "76" or "7-Eleven"
    would leave nothing to match on.
    """
    text = _NOISE.sub(" ", str(name or "").lower())
    tokens = text.split()
    kept = [token for token in tokens if not _HAS_DIGIT.search(token)]
    return " ".join(kept or tokens)


def display_merchant(name: str | None) -> str:
    """The merchant without its varying reference, in the issuer's own casing.

    Naming a stream after whichever charge happened to be seen first would put
    "NETFLIX 0A9X" on the screen. Stripping the same tokens the key drops keeps
    it readable without inventing a brand name we were never given.
    """
    tokens = _NOISE_ANY_CASE.sub(" ", str(name or "")).split()
    kept = [token for token in tokens if not _HAS_DIGIT.search(token)]
    return " ".join(kept or tokens) or str(name or "")


def _parse(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _cadence_for(interval: float) -> tuple[str, float] | None:
    for label, low, high, per_month in CADENCES:
        if low <= interval <= high:
            return label, per_month
    return None


def detect_streams(transactions, *, today: date | None = None) -> list[dict]:
    """Spending that repeats on a schedule, extracted from history.

    Rent, a phone bill and a streaming subscription are commitments, not
    samples: they will recur next month at roughly the same amount whatever the
    daily average says. Averaging them into a daily rate and multiplying by the
    horizon works by accident over thirty days and fails badly over twelve
    months, because it lets a single annual insurance premium inflate every
    month of the projection.

    Deliberately deterministic — this is grouping, differencing and a median. A
    model here would be slower, non-reproducible, and no better at arithmetic.
    """
    as_of = today or date.today()

    by_merchant: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    meta: dict[str, dict] = {}
    for transaction in transactions:
        if not is_eligible_purchase(transaction) or transaction.get("isRefund"):
            continue
        when = _parse(transaction.get("date"))
        amount = float(transaction.get("amount") or 0)
        if when is None or when > as_of or amount <= 0:
            continue
        key = normalise_merchant(transaction.get("merchant"))
        if not key:
            continue
        # Two charges from one merchant on one day are one event for cadence
        # purposes — a split payment, not evidence of a daily subscription.
        by_merchant[key][when] += amount
        meta.setdefault(key, {
            "merchant": display_merchant(transaction.get("merchant")) or key,
            "category": transaction.get("category"),
            "mcc": transaction.get("mcc"),
        })

    streams = []
    for key, charges in by_merchant.items():
        stream = _stream_from(key, charges, meta[key], as_of)
        if stream:
            streams.append(stream)
    return sorted(streams, key=lambda item: item["monthlyAmount"], reverse=True)


def _stream_from(key: str, charges: dict[date, float], meta: dict, as_of: date) -> dict | None:
    dates = sorted(charges)
    if len(dates) < 2:
        return None

    intervals = [(later - earlier).days for earlier, later in zip(dates, dates[1:])]
    typical = median(intervals)
    cadence = _cadence_for(typical)
    if cadence is None:
        return None
    label, per_month = cadence

    # Every gap has to look like the same cadence. One merchant charged on the
    # 1st, the 2nd and the 30th is a habit with a coincidence in it, not a
    # subscription, and projecting it forward would invent money.
    if any(abs(interval - typical) > max(4.0, typical * 0.35) for interval in intervals):
        return None

    amounts = [charges[when] for when in dates]
    typical_amount = median(amounts)
    if typical_amount <= 0:
        return None
    spread = max(abs(amount - typical_amount) for amount in amounts) / typical_amount

    billable = is_billable(meta.get("category"))

    # A utility bill moves with the season: heating in January against nothing
    # in June is a swing of well over a third, and rejecting that would drop
    # the most reliably recurring charge most people have. Where the category
    # bills on a schedule, regular timing is the evidence and the amount is
    # allowed to move. Where it does not, a stable amount is the only thing
    # making the charge look like an arrangement at all, so it is held tight.
    if spread > (0.60 if billable else 0.35):
        return None

    # Two charges is one interval — enough to notice, not enough to be sure.
    # It is reported at lower confidence rather than withheld, because with
    # ninety days of history a monthly bill can only ever have three.
    if len(dates) >= 3 and spread <= (0.30 if billable else 0.15):
        confidence = "high"
    elif len(dates) >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    last_seen = dates[-1]
    due = last_seen + timedelta(days=round(typical))
    if (as_of - last_seen).days > typical * LAPSE_FACTOR:
        return None

    return {
        "key": key,
        "kind": "bill" if billable else "habit",
        "merchant": meta["merchant"],
        "category": meta.get("category"),
        "mcc": meta.get("mcc"),
        "cadence": label,
        "intervalDays": round(typical),
        "amount": round(typical_amount, 2),
        "monthlyAmount": round(typical_amount * per_month, 2),
        "occurrences": len(dates),
        "firstSeen": str(dates[0]),
        "lastSeen": str(last_seen),
        "nextDue": str(due),
        "confidence": confidence,
        "variability": round(spread, 3),
    }


def occurrences_between(stream: dict, start: date, end: date) -> list[date]:
    """The dates this stream is expected to charge inside a window."""
    interval = max(1, int(stream.get("intervalDays") or 0))
    when = _parse(stream.get("lastSeen"))
    if when is None:
        return []
    dates = []
    when += timedelta(days=interval)
    while when <= end:
        if when >= start:
            dates.append(when)
        when += timedelta(days=interval)
    return dates


def commitments(streams) -> list[dict]:
    """Only the streams that represent a standing arrangement to pay."""
    return [stream for stream in streams if stream.get("kind") == "bill"]


def stream_keys(streams) -> set[str]:
    return {stream["key"] for stream in streams}


def split_history(transactions, streams, *, today: date | None = None) -> tuple[list, list]:
    """Separate the transactions a stream explains from everything else.

    The variable baseline must be measured on what is left, or the recurring
    spend gets counted twice — once as a commitment and once inside the daily
    average that the commitment inflated.

    Habits are deliberately left in. They are not projected by date, so their
    history has to stay in the pool that is projected as a rate — removing it
    would delete the spending from the forecast altogether.
    """
    as_of = today or date.today()
    keys = stream_keys(commitments(streams))
    recurring, variable = [], []
    for transaction in transactions:
        if not is_eligible_purchase(transaction):
            continue
        when = _parse(transaction.get("date"))
        if when is None or when > as_of:
            continue
        target = recurring if normalise_merchant(transaction.get("merchant")) in keys else variable
        target.append(transaction)
    return recurring, variable
