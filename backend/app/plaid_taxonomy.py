from __future__ import annotations

# Plaid's personal finance category taxonomy, mapped to the two things the rest
# of the system reasons about: a merchant category code, and the category label
# card terms are written in.
#
# Plaid does return `merchant_category_code`, but only on some transactions —
# 44 of 68 in a sandbox pull. This table covers the rest, so a rule scoped to
# MCC 5812 still matches a restaurant Plaid did not code.
#
# Codes here are the representative one for the category, not the full set:
# they describe what a transaction WAS, where a card rule describes what it
# COVERS. Matching a single code against a rule's list is the right direction.
PFC_TO_MCC: dict[str, tuple[str, str]] = {
    # detailed PFC -> (mcc, our category label)
    "FOOD_AND_DRINK_RESTAURANT": ("5812", "Dining"),
    "FOOD_AND_DRINK_FAST_FOOD": ("5814", "Dining"),
    "FOOD_AND_DRINK_COFFEE": ("5814", "Dining"),
    "FOOD_AND_DRINK_BEER_WINE_AND_LIQUOR": ("5813", "Dining"),
    "FOOD_AND_DRINK_GROCERIES": ("5411", "Groceries"),
    "FOOD_AND_DRINK_VENDING_MACHINES": ("5499", "Groceries"),
    "FOOD_AND_DRINK_OTHER_FOOD_AND_DRINK": ("5812", "Dining"),

    "TRAVEL_FLIGHTS": ("4511", "Air travel"),
    "TRAVEL_LODGING": ("7011", "Hotels"),
    "TRAVEL_RENTAL_CARS": ("7512", "Car rental"),
    "TRAVEL_OTHER_TRAVEL": ("4722", "Travel"),

    "TRANSPORTATION_TAXIS_AND_RIDE_SHARES": ("4121", "Transit"),
    "TRANSPORTATION_PUBLIC_TRANSIT": ("4111", "Transit"),
    "TRANSPORTATION_GAS": ("5541", "Fuel"),
    "TRANSPORTATION_PARKING": ("7523", "Transit"),
    "TRANSPORTATION_TOLLS": ("4784", "Transit"),
    "TRANSPORTATION_BIKES_AND_SCOOTERS": ("4121", "Transit"),
    "TRANSPORTATION_OTHER_TRANSPORTATION": ("4121", "Transit"),

    "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES": ("5399", "Online retail"),
    "GENERAL_MERCHANDISE_ELECTRONICS": ("5732", "Electronics"),
    "GENERAL_MERCHANDISE_CLOTHING_AND_ACCESSORIES": ("5651", "Fashion"),
    "GENERAL_MERCHANDISE_DEPARTMENT_STORES": ("5311", "Department stores"),
    "GENERAL_MERCHANDISE_DISCOUNT_STORES": ("5310", "Wholesale clubs"),
    "GENERAL_MERCHANDISE_SUPERSTORES": ("5300", "Wholesale clubs"),
    "GENERAL_MERCHANDISE_CONVENIENCE_STORES": ("5499", "Groceries"),
    "GENERAL_MERCHANDISE_BOOKSTORES_AND_NEWSSTANDS": ("5942", "Online retail"),
    "GENERAL_MERCHANDISE_GIFTS_AND_NOVELTIES": ("5947", "Online retail"),
    "GENERAL_MERCHANDISE_PET_SUPPLIES": ("5995", "Online retail"),
    "GENERAL_MERCHANDISE_SPORTING_GOODS": ("5941", "Online retail"),
    "GENERAL_MERCHANDISE_OFFICE_SUPPLIES": ("5943", "Online retail"),
    "GENERAL_MERCHANDISE_OTHER_GENERAL_MERCHANDISE": ("5399", "Online retail"),

    "ENTERTAINMENT_STREAMING": ("5815", "Streaming"),
    "ENTERTAINMENT_MUSIC_AND_AUDIO": ("5735", "Streaming"),
    "ENTERTAINMENT_VIDEO_GAMES": ("5816", "Streaming"),
    "ENTERTAINMENT_MOVIES_AND_DVDS": ("7832", "Entertainment"),
    "ENTERTAINMENT_CASINOS_AND_GAMBLING": ("7995", "Entertainment"),
    "ENTERTAINMENT_SPORTING_EVENTS_AMUSEMENT_PARKS_AND_MUSEUMS": ("7991", "Entertainment"),
    "ENTERTAINMENT_OTHER_ENTERTAINMENT": ("7999", "Entertainment"),

    "PERSONAL_CARE_GYMS_AND_FITNESS_CENTERS": ("7997", "Fitness"),
    "PERSONAL_CARE_HAIR_AND_BEAUTY": ("7230", "Beauty"),
    "PERSONAL_CARE_LAUNDRY_AND_DRY_CLEANING": ("7216", "Personal care"),
    "PERSONAL_CARE_OTHER_PERSONAL_CARE": ("7298", "Beauty"),

    "MEDICAL_PRIMARY_CARE": ("8011", "Medical"),
    "MEDICAL_DENTAL_CARE": ("8021", "Medical"),
    "MEDICAL_PHARMACIES_AND_SUPPLEMENTS": ("5912", "Drugstores"),
    "MEDICAL_OTHER_MEDICAL": ("8099", "Medical"),

    "RENT_AND_UTILITIES_INTERNET_AND_CABLE": ("4899", "Utilities"),
    "RENT_AND_UTILITIES_TELEPHONE": ("4814", "Utilities"),
    "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY": ("4900", "Utilities"),
    "RENT_AND_UTILITIES_WATER": ("4900", "Utilities"),
    "RENT_AND_UTILITIES_RENT": ("6513", "Rent"),
    "RENT_AND_UTILITIES_OTHER_UTILITIES": ("4900", "Utilities"),

    "HOME_IMPROVEMENT_HARDWARE": ("5251", "Home improvement"),
    "HOME_IMPROVEMENT_FURNITURE": ("5712", "Home improvement"),
    "HOME_IMPROVEMENT_OTHER_HOME_IMPROVEMENT": ("5200", "Home improvement"),

    "GENERAL_SERVICES_EDUCATION": ("8299", "Education"),
    "GENERAL_SERVICES_INSURANCE": ("6300", "Insurance"),
    "GENERAL_SERVICES_OTHER_GENERAL_SERVICES": ("7399", "Services"),

    "GOVERNMENT_AND_NON_PROFIT_TAX_PAYMENT": ("9311", "Government"),
    "GOVERNMENT_AND_NON_PROFIT_DONATIONS": ("8398", "Government"),

    # The rest of Plaid's taxonomy. Every unmapped detail falls back to a
    # primary, and every unmapped primary falls to "Uncategorised" — which is
    # now excluded from the reward comparison entirely, so a gap here is not a
    # wrong number, it is spending no card can be judged on. Worth closing.
    "FOOD_AND_DRINK_BAKERIES": ("5462", "Dining"),
    "TRAVEL_PUBLIC_TRANSIT": ("4111", "Transit"),
    "TRAVEL_PARKING": ("7523", "Transit"),
    "TRAVEL_GAS": ("5541", "Fuel"),
    "TRAVEL_TAXIS_AND_RIDE_SHARES": ("4121", "Transit"),
    "TRANSPORTATION_CAR_RENTAL": ("7512", "Car rental"),
    "TRANSPORTATION_AUTO_MAINTENANCE": ("7538", "Auto"),
    "TRANSPORTATION_AUTO_PAYMENT": ("5511", "Auto"),

    "GENERAL_MERCHANDISE_SUPERSTORES_AND_WAREHOUSE_CLUBS": ("5300", "Wholesale clubs"),
    "GENERAL_MERCHANDISE_ONLINE_SHOPPING": ("5399", "Online retail"),
    "GENERAL_MERCHANDISE_TOBACCO_AND_VAPE": ("5993", "Online retail"),

    "ENTERTAINMENT_TV_AND_MOVIES": ("5815", "Streaming"),
    "ENTERTAINMENT_MUSIC_AND_AUDIO_SUBSCRIPTIONS": ("5815", "Streaming"),

    "PERSONAL_CARE_OTHER": ("7298", "Beauty"),
    "MEDICAL_EYE_CARE": ("8043", "Medical"),
    "MEDICAL_NURSING_CARE": ("8050", "Medical"),
    "MEDICAL_VETERINARY_SERVICES": ("0742", "Medical"),

    "GENERAL_SERVICES_ACCOUNTING_AND_FINANCIAL_PLANNING": ("8931", "Services"),
    "GENERAL_SERVICES_AUTOMOTIVE": ("7538", "Auto"),
    "GENERAL_SERVICES_CHILDCARE": ("8351", "Services"),
    "GENERAL_SERVICES_CONSULTING_AND_LEGAL": ("8111", "Services"),
    "GENERAL_SERVICES_POSTAGE_AND_SHIPPING": ("4215", "Services"),
    "GENERAL_SERVICES_STORAGE": ("4225", "Services"),

    "HOME_IMPROVEMENT_REPAIR_AND_MAINTENANCE": ("1520", "Home improvement"),
    "HOME_IMPROVEMENT_SECURITY": ("7393", "Home improvement"),

    "RENT_AND_UTILITIES_SEWAGE_AND_WASTE_MANAGEMENT": ("4900", "Utilities"),

    "GOVERNMENT_AND_NON_PROFIT_GOVERNMENT_DEPARTMENTS_AND_AGENCIES": ("9399", "Government"),
}

# Fallback when only the primary category is known.
PFC_PRIMARY_TO_MCC: dict[str, tuple[str, str]] = {
    "FOOD_AND_DRINK": ("5812", "Dining"),
    "TRAVEL": ("4722", "Travel"),
    "TRANSPORTATION": ("4121", "Transit"),
    "GENERAL_MERCHANDISE": ("5399", "Online retail"),
    "ENTERTAINMENT": ("7999", "Entertainment"),
    "PERSONAL_CARE": ("7298", "Beauty"),
    "MEDICAL": ("8099", "Medical"),
    "RENT_AND_UTILITIES": ("4900", "Utilities"),
    "HOME_IMPROVEMENT": ("5200", "Home improvement"),
    "GENERAL_SERVICES": ("7399", "Services"),
    "GOVERNMENT_AND_NON_PROFIT": ("9311", "Government"),
    # Plaid's catch-all. It genuinely tells us nothing, so it stays
    # uncategorised rather than being assigned a code we invented.
}

# Money moving, not money spent. A credit card bill payment, a transfer between
# your own accounts and a loan repayment all appear in the feed and none of them
# earn rewards — counting them would inflate every figure on the dashboard.
NON_PURCHASE_PRIMARIES = {
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "LOAN_PAYMENTS",
    "BANK_FEES",
    "INCOME",
}


def classify(pfc_primary: str | None, pfc_detailed: str | None) -> tuple[str | None, str, bool]:
    """Return (mcc, category label, is_purchase) for a Plaid category pair."""
    primary = (pfc_primary or "").upper()
    detailed = (pfc_detailed or "").upper()

    if primary in NON_PURCHASE_PRIMARIES:
        return None, "Transfers & payments", False

    if detailed in PFC_TO_MCC:
        mcc, label = PFC_TO_MCC[detailed]
        return mcc, label, True

    if primary in PFC_PRIMARY_TO_MCC:
        mcc, label = PFC_PRIMARY_TO_MCC[primary]
        return mcc, label, True

    return None, "Uncategorised", True


# Spending that a payment intermediary such as CardUp can route onto a credit
# card for a fee. It earns nothing today because the biller does not take cards,
# but it is not junk data — it is the largest untapped category most people
# have, and the strategy agent should later weigh the fee against the reward.
REDIRECTABLE_CATEGORIES = {
    "Rent", "Utilities", "Insurance", "Education", "Government", "Medical",
}


def is_redirectable(category: str | None, is_purchase: bool) -> bool:
    """Could this spending be moved onto a card through a payment service?"""
    return bool(is_purchase and category in REDIRECTABLE_CATEGORIES)
