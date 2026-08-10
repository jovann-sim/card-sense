"""Ten reward structures chosen to break the extraction schema.

These are paraphrased from published terms rather than copied, and the figures
are illustrative — the point is the *shape* of each structure, not the rate.
Each entry names what it is designed to stress and what a correct extraction
must contain, so the harness can check rather than eyeball.
"""

from __future__ import annotations

CORPUS = [
    {
        "id": "nominated-category",
        "name": "US Bank Cash+ Visa Signature",
        "stresses": "Holder nominates TWO 5% categories and one 2% category, each capped and requiring enrolment",
        "track": "cashback",
        "terms": """U.S. Bank Cash+ Visa Signature Card. Choose two categories to earn 5% cash back
on the first $2,000 in combined eligible net purchases each quarter.
Eligible 5% categories: home utilities, TV/internet/streaming services, fast food, cell phone providers,
electronics stores, department stores, movie theaters, gyms and fitness centers, furniture stores,
ground transportation, select clothing stores, sporting goods stores.
Choose one everyday category to earn 2% cash back with no cap: gas stations and EV charging,
grocery stores, or restaurants. All other eligible purchases earn 1% cash back.
Categories must be selected each quarter; purchases before selection earn 1%.
No annual fee.""",
        "expect": {"requiresSelection": True, "conditions": {"category_selection", "enrolment"}},
    },
    {
        "id": "reward-currency-choice",
        "name": "Bilt Mastercard",
        "stresses": "Rewards require a transaction count; rent earns only up to a cap; points transfer to many programmes",
        "track": "points",
        "terms": """Bilt Mastercard. Earn 1X point per dollar on rent with no transaction fee,
on up to 100,000 points per calendar year. Earn 3X points on dining, 2X points on travel,
and 1X points on all other purchases.
You must make at least 5 transactions each statement period to earn any points that period.
Points transfer 1:1 to airline and hotel partners including American AAdvantage,
United MileagePlus, and World of Hyatt. No annual fee.""",
        "expect": {"conditions": {"transaction_count"}},
    },
    {
        "id": "transaction-count",
        "name": "Wells Fargo Attune",
        "stresses": "Rate applies to an unusual grab-bag of categories with an enrolment-gated bonus",
        "track": "cashback",
        "terms": """Wells Fargo Attune Card. Earn 4% cash back on self-care, sport, recreation,
impact and entertainment purchases: gym memberships, fitness services, spa services, salons,
sporting events, concerts, movie theaters, public transit, electric vehicle charging,
donations to select charities, and pet supplies.
Earn 1% cash back on all other purchases.
New cardholders earn a $100 cash rewards bonus after spending $500 in purchases
in the first 3 months. No annual fee.""",
        "expect": {"conditions": {"minimum_spend", "new_customer"}},
    },
    {
        "id": "rotating-activation",
        "name": "Discover it Cash Back",
        "stresses": "Category rotates each quarter and must be activated; cap is quarterly",
        "track": "cashback",
        "terms": """Discover it Cash Back. Earn 5% cash back on everyday purchases at different places
each quarter — such as grocery stores, restaurants, gas stations, and .com purchases —
up to the quarterly maximum of $1,500 in purchases, when you activate.
Activation is required each quarter; purchases made before activation earn 1%.
All other purchases earn 1% cash back automatically, with no cap.""",
        "expect": {"conditions": {"enrolment"}, "rotating": True},
    },
    {
        "id": "automatic-top-category",
        "name": "Citi Custom Cash",
        "stresses": "Bonus category is chosen automatically by the issuer from the holder's own top spend",
        "track": "cashback",
        "terms": """Citi Custom Cash Card. Earn 5% cash back on purchases in your top eligible spend category
each billing cycle, up to the first $500 spent, then 1%. You do not choose the category:
it is determined automatically by your highest spend that cycle.
Eligible categories: restaurants, gas stations, grocery stores, select travel, select transit,
select streaming services, drugstores, home improvement stores, fitness clubs, live entertainment.
All other purchases earn 1% cash back, unlimited.""",
        "expect": {"dynamic_category": True},
    },
    {
        "id": "relationship-multiplier",
        "name": "Bank of America Customized Cash Rewards",
        "stresses": "Holder picks the category AND a relationship tier multiplies every rate",
        "track": "cashback",
        "terms": """Bank of America Customized Cash Rewards. Choose one 3% category from:
gas, online shopping, dining, travel, drug stores, or home improvement and furnishings.
Earn 3% in your chosen category and 2% at grocery stores and wholesale clubs,
on the first $2,500 in combined choice-category, grocery and wholesale club purchases each quarter,
then 1%. All other purchases earn 1%.
Preferred Rewards members earn a bonus of 25%, 50% or 75% on all rewards, based on qualifying balances.""",
        "expect": {"requiresSelection": True, "shared_cap": True, "multiplier": True},
    },
    {
        "id": "statement-credits",
        "name": "American Express Platinum",
        "stresses": "Value is mostly fixed statement credits, not an earn rate per dollar",
        "track": "points",
        "terms": """The Platinum Card. Earn 5X Membership Rewards points on flights booked directly with airlines
or with American Express Travel, on up to $500,000 on these purchases per calendar year.
Earn 5X points on prepaid hotels booked on amextravel.com. Earn 1X points on all other eligible purchases.
Benefits include up to $200 in annual airline fee credits, up to $200 in annual Uber Cash,
up to $189 in annual CLEAR Plus credit, and up to $100 in annual Saks credit.
These credits are statement credits, not points, and are forfeited if unused. Annual fee $695.""",
        "expect": {"statement_credits": True},
    },
    {
        "id": "annual-cap-then-base",
        "name": "American Express Blue Cash Preferred",
        "stresses": "Annual (not monthly) cap, then a lower rate on the same category",
        "track": "cashback",
        "terms": """Blue Cash Preferred Card. Earn 6% cash back at U.S. supermarkets on up to $6,000 per year
in purchases, then 1%. Earn 6% cash back on select U.S. streaming subscriptions.
Earn 3% cash back at U.S. gas stations and on transit, including taxis, rideshare, parking,
tolls, trains and buses. Earn 1% on other purchases.
Cash back is received as Reward Dollars that can be redeemed as a statement credit.
Annual fee $95, waived the first year.""",
        "expect": {"annual_cycle": True, "step_down": True},
    },
    {
        "id": "mcc-scoped-points",
        "name": "American Express Gold",
        "stresses": "Several rates scoped to different MCC sets, one annually capped, plus monthly credits",
        "track": "points",
        "terms": """American Express Gold Card. Earn 4X Membership Rewards points at restaurants worldwide,
including takeout and delivery in the U.S., on up to $50,000 in purchases per calendar year, then 1X.
Earn 4X points at U.S. supermarkets on up to $25,000 in purchases per calendar year, then 1X.
Earn 3X points on flights booked directly with airlines or on amextravel.com.
Earn 1X points on all other eligible purchases.
Superstores, specialty stores and warehouse clubs are not U.S. supermarkets and earn 1X.
Receive up to $10 in Uber Cash each month and up to $10 in dining statement credits each month
at participating partners; enrolment is required for both. Annual fee $325.""",
        "expect": {"mcc": True, "exclusions": True, "statement_credits": True},
    },
    {
        "id": "spend-elsewhere",
        "name": "Bank of America Premium Rewards",
        "stresses": "A relationship tier multiplies every rate, and credits are separate from earning",
        "track": "points",
        "terms": """Bank of America Premium Rewards. Earn 2 points per dollar on travel and dining purchases
and 1.5 points per dollar on all other purchases, with no cap.
Preferred Rewards members earn 25%, 50% or 75% more points on every purchase,
based on combined qualifying balances held with Bank of America and Merrill.
Receive up to $100 in airline incidental statement credits annually and
up to $100 in Global Entry or TSA PreCheck credit every four years.
Annual fee $95.""",
        "expect": {"multiplier": True, "statement_credits": True},
    },
]
