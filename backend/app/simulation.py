from __future__ import annotations

from datetime import date

from .agents.ingestion import is_eligible_purchase
from .routing import options as routing_options, service as routing_service
from .welcome import bonus_value

DAYS_PER_YEAR = 365.0

# A card has to beat its fee by more than a rounding error before it is worth
# recommending someone apply for it, open an account and change their habits.
WORTH_SWITCHING = 25.0


def _parse(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def observed_days(transactions) -> int:
    """How long the priced history actually covers.

    Every figure here is annualised against this. A card's fee is yearly, so
    comparing it to three months of rewards would make every premium card look
    like a bad idea and every free one like a certainty.
    """
    dates = [when for row in transactions
             if is_eligible_purchase(row) and (when := _parse(row.get("date")))]
    if not dates:
        return 0
    return max(1, (max(dates) - min(dates)).days + 1)


def optimal_value(agent, transactions, cards, rules) -> float:
    """The best reward obtainable from a set of cards, ignoring who actually paid.

    captured + unclaimed is the optimiser's own total: what perfect card choice
    would have earned across every category, cap and eligibility condition. It
    is independent of attribution, which is what makes it usable for a card the
    user does not hold and has never spent on.
    """
    result = agent.run(transactions, cards, rules)
    return round(result["captured"] + result["unclaimed"], 2)


def assignments(agent, transactions, wallet, rules) -> list[dict]:
    """Which card should carry which category, once caps are respected.

    This is the multi-card answer rather than a single winner: a category can
    exhaust one card's cap and spill onto another, and saying "use card A" when
    A stops paying after $500 is advice that quietly stops being true.
    """
    result = agent.run(transactions, wallet, rules)
    rows = []
    for category in result["categories"]:
        rows.append({
            "category": category["category"],
            "mcc": category.get("mcc", "—"),
            "spend": category["spend"],
            "useCard": category.get("bestCard"),
            "currentCard": category.get("usedCard"),
            "captured": category["captured"],
            "gain": category["unclaimed"],
            "switch": bool(
                category.get("bestCard")
                and category.get("bestCard") not in str(category.get("usedCard") or "")
                and category["unclaimed"] > 0
            ),
            **({"note": category["note"]} if category.get("note") else {}),
        })
    return sorted(rows, key=lambda row: row["gain"], reverse=True)


def card_additions(agent, transactions, wallet, rules, catalog, *, days: int) -> list[dict]:
    """What each card the user does not hold would add, net of its fee.

    Run as a counterfactual: price the whole history again with the card in the
    wallet and subtract. That accounts for caps and for the card only helping
    where it actually beats what is already held — a 4x dining card adds
    nothing to someone who already holds a 4x dining card.
    """
    if not catalog or days <= 0:
        return []

    scale = DAYS_PER_YEAR / days
    base = optimal_value(agent, transactions, wallet, rules)
    held_names = {card.get("name") for card in wallet}

    rows = []
    for entry in catalog:
        if entry.get("name") in held_names or not entry.get("rules"):
            continue
        hypothetical = {
            "cardId": f"catalog::{entry['id']}",
            "name": entry["name"],
            "last4": "0000",
            "network": entry.get("network", "Unknown"),
            "track": entry.get("track", "cashback"),
            "parseStatus": "parsed",
            # No accountId: it is not held, so nothing can be attributed to it.
        }
        with_card = optimal_value(
            agent, transactions, [*wallet, hypothetical],
            {**rules, hypothetical["cardId"]: entry["rules"]},
        )
        added = round((with_card - base) * scale, 2)
        fee = float(entry.get("annualFee") or 0)
        bonus = entry.get("welcomeBonus")
        bonus_worth = bonus_value(bonus, entry.get("track")) if bonus else 0.0

        rows.append({
            "id": entry["id"],
            "card": entry["name"],
            "network": entry.get("network"),
            "track": entry.get("track"),
            "annualFee": fee,
            "rewardPerYear": added,
            # Year one carries the welcome bonus; every year after does not.
            "netFirstYear": round(added + bonus_worth - fee, 2),
            "netOngoing": round(added - fee, 2),
            "welcomeValue": round(bonus_worth, 2),
            "minSpend": float(bonus.get("minSpend")) if bonus else None,
            "windowDays": int(bonus.get("windowDays")) if bonus else None,
            "worthIt": round(added - fee, 2) > WORTH_SWITCHING,
            "headlineRate": entry.get("headlineRate"),
        })
    return sorted(rows, key=lambda row: row["netFirstYear"], reverse=True)


def routing_gains(routable, welcome, *, service_id=None) -> list[dict]:
    """Where paying a service to charge a bill is actually the right move.

    Almost nowhere. Routing for ordinary earn loses on every category the
    product has ever seen, because no consumer card pays more than the two to
    three percent these services charge. The exception is a welcome bonus,
    where the fee is not the cost of earning two percent but the price of
    several hundred dollars at once — and that exception is worth surfacing
    precisely because it looks like the losing trade next to it.
    """
    chosen = routing_service(service_id)
    gains = []

    for row in welcome or []:
        rescue = row.get("rescue")
        if rescue and rescue.get("worthIt"):
            gains.append({
                "kind": "welcome",
                "category": "Bills, to reach a minimum",
                "card": row["card"],
                "service": rescue["serviceName"],
                "route": rescue["spendToRoute"],
                "fee": rescue["fee"],
                "value": rescue["bonusValue"],
                "net": rescue["net"],
                "deadline": row.get("deadline"),
                "why": (
                    f"Paying {rescue['fee']:,.2f} to close a {row['gap']:,.2f} gap "
                    f"buys a {rescue['bonusValue']:,.2f} bonus before {row.get('deadline')}."
                ),
            })

    for row in routable or []:
        if row.get("worthIt"):
            gains.append({
                "kind": "ongoing",
                "category": row["category"],
                "card": row.get("bestCard"),
                "service": row["serviceName"],
                "route": row["spend"],
                "fee": row["fee"],
                "value": row["reward"],
                "net": row["net"],
                "why": row["verdict"],
            })
    return sorted(gains, key=lambda row: row["net"], reverse=True)


def plan(agent, transactions, wallet, rules, catalog, routable, welcome, *, service_id=None) -> dict:
    """One ranked answer to "what should I actually do".

    The pieces are computed separately because they are different kinds of
    action — reassign a category, apply for a card, pay a fee to reach a bonus —
    but a user wants them in one list, ordered by what they are worth, with the
    arithmetic attached.
    """
    days = observed_days(transactions)
    scale = DAYS_PER_YEAR / days if days else 0.0

    current = agent.run(transactions, wallet, rules)
    moves = assignments(agent, transactions, wallet, rules)
    additions = card_additions(agent, transactions, wallet, rules, catalog, days=days)
    gains = routing_gains(routable, welcome, service_id=service_id)

    switchable = round(sum(row["gain"] for row in moves if row["switch"]), 2)
    # Ranked by first-year value, because that is what people compare — but
    # recommended on ongoing value, because a card whose bonus covers its fee
    # once and loses money every year after is not a card to recommend. The
    # Venture X on this spending adds $363 against a $395 fee: a $943 first
    # year, and a small loss forever after.
    best_addition = max(
        (row for row in additions if row["worthIt"]),
        key=lambda row: row["netOngoing"], default=None,
    )

    steps = []
    # Eight separate "move this category to that card" lines describe one
    # decision. Grouped by the card they all point at, it becomes an
    # instruction a person can follow in a single sitting.
    by_card: dict[str, list[dict]] = {}
    for row in moves:
        if row["switch"] and row["gain"] > 0:
            by_card.setdefault(row["useCard"], []).append(row)

    for card_name, rows in by_card.items():
        rows.sort(key=lambda row: row["gain"], reverse=True)
        total = round(sum(row["gain"] for row in rows), 2)
        named = ", ".join(row["category"].lower() for row in rows[:3])
        rest = len(rows) - 3
        steps.append({
            "kind": "reassign",
            "rank": 0,
            "value": total,
            "valueWindow": "over the period priced",
            "card": card_name,
            "categories": [row["category"] for row in rows],
            "title": (
                f"Move {len(rows)} categories to {card_name}"
                if len(rows) > 1 else
                f"Put {rows[0]['category'].lower()} on {card_name}"
            ),
            "detail": (
                f"{named}{f' and {rest} more' if rest > 0 else ''} — "
                f"{sum(row['spend'] for row in rows):,.2f} of spending currently earning "
                f"{sum(row['captured'] for row in rows):,.2f}, worth {total:,.2f} more on {card_name}."
            ),
        })
    for gain in gains:
        steps.append({
            "kind": f"route-{gain['kind']}",
            "rank": 0,
            "value": gain["net"],
            "valueWindow": "one-time" if gain["kind"] == "welcome" else "over the period priced",
            "title": (
                f"Route {gain['route']:,.0f} through {gain['service']} to reach {gain['card']}'s bonus"
                if gain["kind"] == "welcome" else
                f"Route {gain['category'].lower()} through {gain['service']}"
            ),
            "detail": gain["why"],
        })
    if best_addition:
        steps.append({
            "kind": "acquire",
            "rank": 0,
            "value": best_addition["netOngoing"],
            "valueWindow": "per year, net of fee",
            "title": f"Consider {best_addition['card']}",
            "detail": (
                f"On this spending it would add {best_addition['rewardPerYear']:,.2f} a year "
                f"against a {best_addition['annualFee']:,.0f} fee, so "
                f"{best_addition['netOngoing']:,.2f} a year ongoing"
                + (
                    f", plus a {best_addition['welcomeValue']:,.0f} welcome bonus for "
                    f"{best_addition['minSpend']:,.0f} of spend in {best_addition['windowDays']} days."
                    if best_addition["welcomeValue"] else "."
                )
            ),
        })

    steps.sort(key=lambda step: step["value"], reverse=True)
    for index, step in enumerate(steps):
        step["rank"] = index + 1

    return {
        "observedDays": days,
        "capturedNow": current["captured"],
        "bestWithWallet": round(current["captured"] + current["unclaimed"], 2),
        "reassignableValue": switchable,
        "annualisedGap": round(current["unclaimed"] * scale, 2),
        "assignments": moves,
        "additions": additions,
        "routing": gains,
        "steps": steps[:8],
        "service": routing_service(service_id).id,
    }
