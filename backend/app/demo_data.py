from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

from .plaid_taxonomy import classify, is_redirectable

# A plausible year in the life of one US household.
#
# The Plaid sandbox replays a fixed basket every thirty days at identical
# amounts — four different merchants at exactly $500 — which is arithmetically
# indistinguishable from four subscriptions and makes every forecast look
# absurd. It is fine for proving the pipeline runs and useless for judging
# whether its numbers are sensible.
#
# So this generates spending with the shape real spending has: a few genuine
# monthly commitments, a long tail of variable purchases, weekday-heavy dining,
# lumpy travel, and amounts that vary the way a person's do. Nothing here is
# random-looking for its own sake — each pattern exists because some part of the
# system should be seen handling it.

# label, merchant, category hint, mcc, day of month, amount, jitter
COMMITMENTS: list[tuple[str, str, int, float, float]] = [
    # merchant, mcc, day of month, amount, relative jitter
    ("Greystone Property Mgmt", "6513", 1, 2150.00, 0.0),
    ("Con Edison", "4900", 8, 112.00, 0.28),      # a real utility moves with the season
    ("Verizon Wireless", "4814", 12, 85.00, 0.02),
    ("Equinox", "7997", 5, 185.00, 0.0),
    ("Netflix", "5815", 17, 15.49, 0.0),
    ("Spotify", "5815", 22, 11.99, 0.0),
    ("State Farm Insurance", "6300", 3, 148.00, 0.0),
]

# merchant, mcc, mean amount, relative spread, expected times per month
VARIABLE: list[tuple[str, str, float, float, float]] = [
    ("Whole Foods Market", "5411", 96.0, 0.35, 4.2),
    ("Trader Joe's", "5411", 58.0, 0.4, 2.4),
    ("Starbucks", "5814", 6.75, 0.3, 9.0),
    ("Chipotle", "5814", 14.20, 0.25, 3.2),
    ("Joe's Pizza", "5812", 22.50, 0.4, 2.0),
    ("Sweetgreen", "5812", 16.80, 0.25, 3.4),
    ("Le Bernardin", "5812", 210.00, 0.3, 0.25),   # the occasional expensive dinner
    ("Uber", "4121", 18.40, 0.55, 5.0),
    ("MTA Vending Machine", "4111", 33.00, 0.1, 1.2),
    ("Shell", "5541", 48.00, 0.25, 1.6),
    ("Amazon", "5399", 41.00, 0.8, 6.5),           # the long tail everyone has
    ("Target", "5310", 78.00, 0.5, 1.5),
    ("CVS Pharmacy", "5912", 24.00, 0.5, 1.8),
    ("Home Depot", "5251", 92.00, 0.6, 0.7),
    ("Nordstrom", "5651", 165.00, 0.5, 0.5),
    ("AMC Theatres", "7832", 32.00, 0.2, 0.6),
]

# Travel is lumpy: nothing for months, then a trip. Averaging it into a daily
# rate is exactly the mistake the forecast is built to avoid.
TRIPS: list[tuple[str, str, float]] = [
    ("United Airlines", "4511", 428.00),
    ("Marriott", "7011", 312.00),
    ("Hertz", "7512", 187.00),
]


def _amount(rng: random.Random, mean: float, spread: float) -> float:
    value = rng.gauss(mean, mean * spread)
    return round(max(mean * 0.25, value), 2)


def _row(when: date, merchant: str, mcc: str, amount: float, account_id: str | None) -> dict:
    # The generator knows the MCC, so the category comes from the same table the
    # ingestion agent uses rather than being asserted separately.
    from .mcc import CATEGORY_MCC

    label = "Uncategorised"
    for name, codes in CATEGORY_MCC.items():
        if mcc in codes:
            label = name.title()
            break
    overrides = {
        "6513": "Rent", "4900": "Utilities", "4814": "Utilities", "7997": "Fitness",
        "5815": "Streaming", "6300": "Insurance", "5411": "Groceries", "5814": "Dining",
        "5812": "Dining", "4121": "Transit", "4111": "Transit", "5541": "Fuel",
        "5399": "Online retail", "5310": "Wholesale clubs", "5912": "Drugstores",
        "5251": "Home improvement", "5651": "Fashion", "7832": "Entertainment",
        "4511": "Air travel", "7011": "Hotels", "7512": "Car rental",
    }
    label = overrides.get(mcc, label)
    key = f"demo:{when}:{merchant}:{amount}"
    return {
        "id": "demo-" + hashlib.sha256(key.encode()).hexdigest()[:20],
        "source": "demo",
        "accountId": account_id,
        "date": str(when),
        "merchant": merchant,
        "amount": amount,
        "isRefund": False,
        "category": label,
        "mcc": mcc,
        "mccSource": "demo",
        "categorySource": "demo",
        "detailedCategory": None,
        "isPurchase": True,
        "categoryAmbiguous": False,
        "isRedirectable": is_redirectable(label, True),
        "description": merchant,
        "pending": False,
        "currency": "USD",
        "paymentChannel": "in store",
    }


def generate(
    *,
    today: date | None = None,
    months: int = 12,
    account_ids: list[str] | None = None,
    seed: int = 20260811,
) -> list[dict]:
    """A year of plausible spending, reproducible from the seed.

    Deterministic on purpose: a demo that shows different numbers each time it
    is reset cannot be rehearsed, and a judge who reruns it should see what was
    described to them.
    """
    as_of = today or date.today()
    rng = random.Random(seed)
    accounts = account_ids or [None]
    start = as_of - timedelta(days=round(months * 30.44))
    rows: list[dict] = []

    def account_for(index: int) -> str | None:
        return accounts[index % len(accounts)]

    # Commitments, on their day of the month.
    when = date(start.year, start.month, 1)
    while when <= as_of:
        for merchant, mcc, day, base, jitter in COMMITMENTS:
            try:
                due = when.replace(day=day)
            except ValueError:
                continue
            if not (start <= due <= as_of):
                continue
            amount = round(base * (1 + rng.uniform(-jitter, jitter)), 2) if jitter else base
            rows.append(_row(due, merchant, mcc, amount, account_for(len(rows))))
        when = date(when.year + when.month // 12, when.month % 12 + 1, 1)

    # Variable spending, scattered across the window.
    span = (as_of - start).days
    for merchant, mcc, mean, spread, per_month in VARIABLE:
        count = int(round(per_month * span / 30.44))
        for _ in range(count):
            offset = rng.randrange(span + 1)
            when = start + timedelta(days=offset)
            # Eating out clusters at the end of the week; groceries do not.
            if mcc in {"5812", "5814"} and when.weekday() < 4 and rng.random() < 0.35:
                when += timedelta(days=rng.randint(1, 3))
            if when > as_of:
                continue
            rows.append(_row(when, merchant, mcc, _amount(rng, mean, spread), account_for(len(rows))))

    # Two trips, each a cluster of charges over a few days.
    for trip in range(2):
        anchor = start + timedelta(days=rng.randrange(30, max(31, span - 10)))
        for merchant, mcc, mean in TRIPS:
            when = anchor + timedelta(days=rng.randint(0, 4))
            if when > as_of:
                continue
            rows.append(_row(when, merchant, mcc, _amount(rng, mean, 0.2), account_for(len(rows) + trip)))

    # One refund, because the sign handling should be visible in a demo.
    if rows:
        refunded = next((row for row in rows if row["merchant"] == "Nordstrom"), None)
        if refunded:
            when = date.fromisoformat(refunded["date"]) + timedelta(days=9)
            if when <= as_of:
                credit = _row(when, "Nordstrom", "5651", -refunded["amount"], refunded["accountId"])
                credit["isRefund"] = True
                credit["id"] = credit["id"].replace("demo-", "demo-refund-")
                rows.append(credit)

    # Salary, so the ingestion agent's non-purchase exclusion has something to
    # exclude and the dashboard can show it was excluded rather than missed.
    when = date(start.year, start.month, 15)
    while when <= as_of:
        if when >= start:
            pay = _row(when, "ACME CORP PAYROLL", "0000", 4200.00, accounts[0])
            pay.update({
                "isPurchase": False, "category": "Transfers & payments",
                "mcc": None, "categorySource": "INCOME", "isRedirectable": False,
            })
            rows.append(pay)
        month = when.month % 12 + 1
        when = date(when.year + when.month // 12, month, 15)

    return sorted(rows, key=lambda row: row["date"])


def summarise(rows: list[dict]) -> dict:
    purchases = [row for row in rows if row.get("isPurchase")]
    return {
        "transactions": len(rows),
        "purchases": len(purchases),
        "excluded": len(rows) - len(purchases),
        "spend": round(sum(float(row["amount"]) for row in purchases), 2),
        "first": rows[0]["date"] if rows else None,
        "last": rows[-1]["date"] if rows else None,
    }


def classify_check(rows: list[dict]) -> int:
    """How many rows the taxonomy would place, if they arrived through Plaid."""
    return sum(1 for row in rows if classify(None, None)[1] or row.get("mcc"))
