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
