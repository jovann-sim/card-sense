from __future__ import annotations

from dataclasses import dataclass

# Bill-payment services, which charge a card and pay the biller by transfer.
#
# The product exists because a landlord will not take a Visa. These services
# will, for a percentage — and that percentage is almost always larger than the
# reward, so the honest default answer is "do not do this". Modelling them
# anyway matters, because there is one case where the arithmetic flips: a
# welcome bonus with a minimum spend requirement, where a fee is not a cost of
# earning 2% but the price of unlocking several hundred dollars at once.
@dataclass(frozen=True)
class Service:
    id: str
    name: str
    feeRate: float
    region: str
    note: str


SERVICES: tuple[Service, ...] = (
    Service("plastiq", "Plastiq", 0.029, "US",
            "Pays rent, tuition and invoices by cheque or transfer."),
    Service("melio", "Melio", 0.029, "US",
            "Aimed at business payables; free by bank transfer, 2.9% by card."),
    Service("cardup", "CardUp", 0.026, "SG",
            "The original of this category, Singapore and Hong Kong only."),
)

DEFAULT_SERVICE = "plastiq"


def service(identifier: str | None) -> Service:
    wanted = (identifier or DEFAULT_SERVICE).lower()
    return next((item for item in SERVICES if item.id == wanted), SERVICES[0])


def price(spend: float, reward_rate: float, fee_rate: float) -> dict:
    """What routing this spending through a fee actually nets."""
    fee = spend * fee_rate
    reward = spend * reward_rate
    return {
        "fee": round(fee, 2),
        "reward": round(reward, 2),
        "net": round(reward - fee, 2),
        "breakEvenRate": round(fee_rate, 4),
    }


def options(spend: float, reward_rate: float) -> list[dict]:
    """Every service, priced, cheapest first — so the choice is visible."""
    priced = []
    for item in SERVICES:
        numbers = price(spend, reward_rate, item.feeRate)
        priced.append({
            "service": item.id,
            "name": item.name,
            "region": item.region,
            "feeRate": item.feeRate,
            "note": item.note,
            **numbers,
        })
    return sorted(priced, key=lambda row: row["net"], reverse=True)


def bonus_case(gap: float, bonus_value: float, fee_rate: float) -> dict | None:
    """Routing to reach a welcome bonus, where the fee buys the bonus.

    This is the only version of this trade that is reliably worth making, and
    it is the reason the feature exists rather than a footnote to it.
    """
    if gap <= 0 or bonus_value <= 0:
        return None
    fee = gap * fee_rate
    return {
        "spendToRoute": round(gap, 2),
        "fee": round(fee, 2),
        "bonusValue": round(bonus_value, 2),
        "net": round(bonus_value - fee, 2),
        "worthIt": bonus_value > fee,
    }


def verdict(net: float, category: str, service_name: str) -> str:
    """One sentence a person can act on, in the direction the numbers point."""
    if net > 0:
        return (
            f"Routing {category.lower()} through {service_name} nets "
            f"{net:,.2f} after the fee."
        )
    return (
        f"Do not route {category.lower()} through {service_name} for the reward alone — "
        f"the fee costs {abs(net):,.2f} more than the card pays back. It is only "
        "worth doing to reach a welcome-bonus minimum."
    )
