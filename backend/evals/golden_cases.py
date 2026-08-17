"""Machine-readable golden cases for CardSense's five production agents.

These cases are deliberately small enough to audit by hand. They are not
copies of implementation output: each expected monetary value can be derived
from the input on paper, while the safety cases state when an agent must
exclude, preserve, or decline instead of guessing.
"""

from __future__ import annotations


WALLET = [
    {
        "cardId": "bonus", "name": "Bonus Card", "last4": "1111",
        "accountId": "bonus-acct", "track": "cashback", "parseStatus": "parsed",
    },
    {
        "cardId": "flat", "name": "Flat Card", "last4": "2222",
        "accountId": "flat-acct", "track": "cashback", "parseStatus": "parsed",
    },
]

RULES = {
    "bonus": [
        {
            "categoryLabel": "Dining", "valuePerDollar": 0.05,
            "capSpend": 100, "cycleLabel": "per month",
        },
        {"categoryLabel": "Everything else", "valuePerDollar": 0.01},
    ],
    "flat": [
        {"categoryLabel": "Everything else", "valuePerDollar": 0.02},
    ],
}


INGESTION_CASES = [
    {
        "id": "restaurant-normalisation",
        "risk": "correctness",
        "operation": "normalise",
        "input": {
            "transaction_id": "restaurant", "amount": "42.50", "account_id": "flat-acct",
            "personal_finance_category": {
                "primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_RESTAURANT",
            },
        },
        "expect": {
            "amount": 42.5, "category": "Dining", "mcc": "5812",
            "mccSource": "inferred", "isPurchase": True, "isRefund": False,
        },
    },
    {
        "id": "transfer-excluded",
        "risk": "safety",
        "operation": "normalise",
        "input": {
            "transaction_id": "transfer", "amount": 500,
            "personal_finance_category": {
                "primary": "TRANSFER_OUT", "detailed": "TRANSFER_OUT_ACCOUNT_TRANSFER",
            },
        },
        "expect": {"category": "Transfers & payments", "mcc": None, "isPurchase": False},
    },
    {
        "id": "coverage-gap-reported",
        "risk": "safety",
        "operation": "summary",
        "input": [
            {"isPurchase": True, "mcc": "5812", "mccSource": "plaid", "accountId": "linked"},
            {"isPurchase": True, "mcc": None, "accountId": "unlinked"},
        ],
        "linkedAccountIds": ["linked"],
        "expect": {
            "purchases": 2, "withMcc": 1, "mccCoverage": 0.5,
            "unlinkedToCard": 1, "degradedCount": 2,
        },
    },
]


CARD_INTELLIGENCE_CASES = [
    {
        "id": "structured-rate-and-cap",
        "risk": "correctness",
        "card": {"name": "Golden Card", "track": "cashback", "termsText": "Golden terms."},
        "extraction": {
            "confidence": 0.95,
            "documentSummary": "Five percent on dining, then one percent.",
            "characteristics": {"issuer": "Golden Bank", "annualFee": 95, "currency": "USD"},
            "rules": [
                {
                    "categoryLabel": "Dining", "tier": "bonus", "mccCodes": ["5812"],
                    "cap": 600, "capType": "spend", "cycleLabel": "per month",
                    "rewards": [{"rewardType": "cashback", "rateValue": 5, "rateUnit": "percent"}],
                },
                {
                    "categoryLabel": "Everything else", "tier": "base",
                    "rewards": [{"rewardType": "cashback", "rateValue": 1, "rateUnit": "percent"}],
                },
            ],
        },
        "expect": {
            "status": "parsed", "confidence": 0.95, "annualFee": 95,
            "rules.0.categoryLabel": "Dining", "rules.0.valuePerDollar": 0.05,
            "rules.0.capSpend": 600.0, "rules.0.cycleLabel": "per month",
            "rules.1.valuePerDollar": 0.01, "source.locator": "pasted text",
        },
    },
    {
        "id": "low-confidence-abstention",
        "risk": "safety",
        "card": {"name": "Ambiguous Card", "track": "cashback", "termsText": "Maybe five percent."},
        "extraction": {
            "confidence": 0.1,
            "rules": [{
                "categoryLabel": "Dining",
                "rewards": [{"rewardType": "cashback", "rateValue": 5, "rateUnit": "percent"}],
            }],
        },
        "expect": {"status": "failed", "failureReason": "low_confidence", "rules": []},
    },
    {
        "id": "transient-failure-preserves-rules",
        "risk": "recovery",
        "card": {"name": "Existing Card", "track": "cashback", "termsText": "Temporarily unavailable."},
        "error": {"reason": "rate_limited", "detail": "quota"},
        "previous": {
            "rules": [{"categoryLabel": "Everything else", "valuePerDollar": 0.02}],
            "confidence": 0.9,
            "source": {
                "label": "Issuer terms page", "locator": "https://issuer.test/terms",
                "retrievedAt": "2026-08-01",
            },
        },
        "expect": {
            "status": "stale", "failureReason": "rate_limited", "confidence": 0.9,
            "rules.0.valuePerDollar": 0.02, "source.retrievedAt": "2026-08-01",
        },
    },
]


STRATEGY_CASES = [
    {
        "id": "best-card-and-leakage",
        "risk": "correctness",
        "transactions": [
            {
                "category": "Dining", "mcc": "5812", "amount": 100,
                "accountId": "flat-acct", "date": "2026-08-10",
            },
        ],
        "wallet": WALLET,
        "rules": RULES,
        "expect": {
            "captured": 2.0, "unclaimed": 3.0,
            "categories.0.spend": 100.0, "categories.0.bestCard": "Bonus Card",
            "categories.0.usedCard": "Flat Card ••2222",
        },
    },
    {
        "id": "cap-step-down",
        "risk": "correctness",
        "transactions": [
            {
                "category": "Dining", "mcc": "5812", "amount": 150,
                "accountId": "bonus-acct", "date": "2026-08-10",
            },
        ],
        "wallet": WALLET,
        "rules": RULES,
        # $100 at 5% plus $50 at 1% is captured. The flat card would return
        # 2% on the $50 above the cap, leaving exactly fifty cents unclaimed.
        "expect": {"captured": 5.5, "unclaimed": 0.5, "categories.0.bestCard": "Bonus Card"},
    },
    {
        "id": "conditional-rate-fails-closed",
        "risk": "safety",
        "transactions": [
            {
                "category": "Dining", "mcc": "5812", "amount": 100,
                "accountId": "flat-acct", "date": "2026-08-10",
            },
        ],
        "wallet": WALLET,
        "rules": {
            "bonus": [{
                "categoryLabel": "Dining", "valuePerDollar": 0.10,
                "conditions": [{"kind": "enrolment", "description": "Activation required."}],
            }],
            "flat": [{"categoryLabel": "Everything else", "valuePerDollar": 0.02}],
        },
        "expect": {
            "captured": 2.0, "unclaimed": 0.0,
            "categories.0.bestCard": "Flat Card",
            "categories.0.flags.0": "conditional-rate",
        },
    },
]


FORECAST_CASES = [
    {
        "id": "declared-plan-only",
        "risk": "correctness",
        "today": "2026-08-10",
        "transactions": [],
        "planned": [{
            "id": "laptop", "kind": "purchase", "label": "Laptop",
            "startDate": "2026-08-20", "amount": 100, "categories": ["Retail"],
        }],
        "expect": {
            "horizonDays": 31, "baselineSpend": 0.0, "plannedSpend": 100.0,
            "projectedSpend": 100.0, "quality": "none",
        },
    },
    {
        "id": "observed-leakage-cost",
        "risk": "correctness",
        "today": "2026-08-10",
        "transactions": [{"date": "2026-08-10", "amount": 100, "isPurchase": True}],
        "planned": [],
        "leakageRate": 0.04,
        "expect": {
            "horizonDays": 31, "baselineSpend": 3100.0, "projectedSpend": 3100.0,
            "quality": "limited", "doNothingCost": 124.0,
        },
    },
    {
        "id": "pending-and-transfer-excluded",
        "risk": "safety",
        "today": "2026-08-10",
        "transactions": [
            {"date": "2026-08-10", "amount": 500, "isPurchase": False},
            {"date": "2026-08-10", "amount": 200, "isPurchase": True, "pending": True},
        ],
        "planned": [],
        "expect": {
            "baselineSpend": 0.0, "projectedSpend": 0.0,
            "historyDays": 0, "quality": "none",
        },
    },
]


ADVISORY_CASES = [
    {
        "id": "grounded-financial-action",
        "risk": "correctness",
        "wallet": WALLET,
        "strategy": {
            "categories": [{
                "category": "Dining", "bestCard": "Bonus Card",
                "unclaimed": 3.0, "flags": [],
            }],
        },
        "forecast": {"quality": "good", "doNothingWindow": "over the next month"},
        "expect": {
            "length": 1, "0.card.name": "Bonus Card", "0.card.last4": "1111",
            "0.impact": 3.0, "0.headline": "Use Bonus Card for Dining",
        },
        "allowedImpacts": [3.0],
    },
    {
        "id": "invented-model-claims-rejected",
        "risk": "safety",
        "wallet": WALLET,
        "strategy": {
            "categories": [{
                "category": "Dining", "bestCard": "Bonus Card",
                "unclaimed": 3.0, "flags": [],
            }],
        },
        "forecast": {},
        "wording": {
            "recommendations": [{
                "category": "Dining", "headline": "Use Imaginary Card for 99% back",
                "body": "Imaginary Card returns $999 immediately.",
            }],
        },
        "expect": {
            "length": 1, "0.card.name": "Bonus Card", "0.impact": 3.0,
            "0.headline": "Use Bonus Card for Dining",
        },
        "forbiddenText": ["Imaginary", "99%", "$999"],
        "allowedImpacts": [3.0],
    },
    {
        "id": "unknown-card-declined",
        "risk": "safety",
        "wallet": WALLET,
        "strategy": {
            "categories": [{
                "category": "Dining", "bestCard": "Not In Wallet",
                "unclaimed": 20.0, "flags": [],
            }],
        },
        "forecast": {},
        "expect": {"length": 0},
        "allowedImpacts": [],
    },
]


CASES_BY_AGENT = {
    "ingestion": INGESTION_CASES,
    "card-intelligence": CARD_INTELLIGENCE_CASES,
    "strategy": STRATEGY_CASES,
    "forecast": FORECAST_CASES,
    "advisory": ADVISORY_CASES,
}

