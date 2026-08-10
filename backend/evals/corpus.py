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
        "name": "UOB Lady's Card",
        "stresses": "Holder nominates the bonus category; a linked savings account raises the rate",
        "track": "miles",
        "terms": """UOB Lady's Card. Cardmembers nominate ONE preferred spend category to earn bonus UNI$.
Selectable categories: Beauty & Wellness, Dining, Entertainment, Family, Fashion, Transport, Travel.
Earn 10 UNI$ per S$5 spent in your nominated category (4 miles per S$1), capped at 3,600 UNI$ per calendar quarter.
All other retail spend earns the base rate of 1 UNI$ per S$5 (0.4 miles per S$1), no cap.
Cardmembers who maintain a UOB One Account earn an additional 0.2 miles per S$1 on nominated categories.
Excluded: insurance premiums, utility bills, government payments, top-ups to payment wallets.
Annual fee S$196.20 waived for the first year. Minimum annual income S$30,000.""",
        "expect": {"requiresSelection": True, "conditions": {"category_selection", "banking_relationship"}},
    },
    {
        "id": "reward-currency-choice",
        "name": "DBS yuu Card",
        "stresses": "Holder chooses yuu Points or cash back; merchant-scoped; minimum spend unlocks a higher tier",
        "track": "cashback",
        "terms": """DBS yuu Card. Cardmembers choose how they are rewarded: yuu Points OR cash back.
Earn 18% back at yuu partners — Cold Storage, Giant, Guardian, 7-Eleven, KFC, Pizza Hut, Duty Free Singapore —
when you spend a minimum of S$600 in a calendar month. Without the minimum spend, partner spend earns 5%.
Rewards at partners are capped at S$60 cash back or 6,000 yuu Points per calendar month.
All other spend earns 0.3% cash back, or 0.4 yuu Points per S$1, with no cap.
Online food delivery via foodpanda and Deliveroo earns the partner rate.
Excluded: AXS, bill payments, insurance, top-ups. Annual fee S$196.20 waived for two years.""",
        "expect": {"reward_choice": True, "merchants": True},
    },
    {
        "id": "transaction-count",
        "name": "UOB One Card",
        "stresses": "Rebate requires a minimum NUMBER of transactions as well as a spend amount, in tiers",
        "track": "cashback",
        "terms": """UOB One Card. Quarterly cash rebate requires a minimum of 5 card transactions per statement month
in each month of the quarter, and a minimum spend in every month of the quarter.
Spend at least S$500 each month: rebate S$50 per quarter.
Spend at least S$1,000 each month: rebate S$100 per quarter.
Spend at least S$2,000 each month: rebate S$200 per quarter.
Missing the transaction count or the minimum spend in any month forfeits the rebate for the whole quarter.
Excluded: AXS, SAM, iBanking bill payments, insurance premiums.""",
        "expect": {"conditions": {"minimum_spend", "transaction_count"}, "statement_credits": True},
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
        "name": "Citi Rewards Card (SG)",
        "stresses": "Bonus is scoped to specific MCCs with a long exclusion list; cap stated in points",
        "track": "miles",
        "terms": """Citi Rewards Card. Earn 10X Citi ThankYou Points on shopping — apparel, department stores,
bags and shoes — and on online purchases in these categories, equal to 4 miles per S$1.
Capped at 10,000 bonus points per statement month.
Earn 1X point per S$1 on all other retail spend, equal to 0.4 miles per S$1.
Online travel, mobile wallet top-ups, utilities, insurance, education and government
transactions are excluded from the 10X rate and earn 1X.
Merchant category codes for the bonus include 5311, 5611, 5621, 5631, 5641, 5651, 5661, 5691, 5699.""",
        "expect": {"mcc": True, "exclusions": True},
    },
    {
        "id": "spend-elsewhere",
        "name": "HSBC Revolution + Everyday Global",
        "stresses": "Rate depends on spending on a DIFFERENT product, and the cap is in points not dollars",
        "track": "miles",
        "terms": """HSBC Revolution Card. Earn 10X Reward points (4 miles per S$1) on online, dining and
entertainment spend. Bonus points are capped at 9,000 Reward points per calendar month.
Cardmembers who also hold an HSBC Everyday Global Account and make at least S$2,000 of
eligible spend on that account in the same month earn an additional 1X Reward point per S$1.
All other eligible spend earns 1X Reward point per S$1, with no cap.
Annual fee waived permanently. Minimum annual income S$30,000.""",
        "expect": {"conditions": {"spend_elsewhere", "banking_relationship"}, "reward_cap": True},
    },
]
