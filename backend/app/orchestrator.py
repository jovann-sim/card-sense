from __future__ import annotations

from datetime import date, datetime, timezone
from math import isfinite
import uuid
from time import perf_counter

from .agents.advisory import AdvisoryAgent
from .agents.card_intelligence import CardIntelligenceAgent
from .agents.forecast import ForecastAgent
from .agents.ingestion import IngestionAgent, is_eligible_purchase
from .agents.runtime import GeminiRuntime
from .agents.strategy import StrategyAgent, VALUATIONS
from .models import Snapshot


READ_MODEL_VERSION = 4


AGENTS = [
    ("ingestion", "Ingestion"), ("card-intelligence", "Card intelligence"),
    ("strategy", "Simulation & strategy"), ("forecast", "Forecast"),
    ("advisory", "Advisory"),
]


def _numeric_advice_value(value) -> float:
    """Treat untrusted model/legacy advice values as zero unless truly numeric."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if isfinite(number) else 0.0


def transaction_totals(transactions) -> dict[str, float]:
    """Separate purchase activity from credits without losing net direction."""
    amounts = [
        float(transaction.get("amount", 0))
        for transaction in transactions
        if is_eligible_purchase(transaction)
    ]
    spend = sum(amount for amount in amounts if amount > 0)
    refunds = -sum(amount for amount in amounts if amount < 0)

    def total(rows) -> float:
        return round(sum(float(row.get("amount") or 0) for row in rows), 2)

    eligible = [t for t in transactions if is_eligible_purchase(t)]
    excluded = [t for t in transactions if t.get("isPurchase") is False]
    uncategorised = [t for t in eligible if t.get("category") in (None, "Uncategorised", "uncategorized")]
    redirectable = [t for t in eligible if t.get("isRedirectable")]

    return {
        "spend": round(spend, 2),
        "refunds": round(refunds, 2),
        "netSpend": round(spend - refunds, 2),
        # What was left out, and why. A user whose dashboard shows less than
        # their statement is owed an explanation rather than a smaller number.
        "excludedSpend": total(excluded),
        "excludedCount": len(excluded),
        # Purchases with no category, so no card rule can claim them. Left out
        # of the comparison rather than quietly earning the base rate, which
        # would flatter every card equally.
        "uncategorisedSpend": total(uncategorised),
        "uncategorisedCount": len(uncategorised),
        # Bills that earn nothing because the biller takes no cards. A payment
        # service could route them for a fee; the optimiser will weigh that.
        "redirectableSpend": total(redirectable),
        "redirectableCount": len(redirectable),
    }


def project_catalog(store, uid, wallet):
    """Project every held card into All cards, including user-added cards."""
    catalog = store.get_subcollection(uid, "catalog")
    held_names = {card.get("name") for card in wallet}
    rows = [{**item, "held": item.get("name") in held_names} for item in catalog]
    catalog_names = {item.get("name") for item in rows}

    for card in wallet:
        if card.get("name") in catalog_names:
            continue
        rules = card.get("rules") or (
            store.get_global_doc("card_rules", card["cardId"]) or {}
        ).get("rules", [])
        headline = ", ".join(
            f"{rule.get('rate', '—')} {rule.get('categoryLabel', '').lower()}".strip()
            for rule in rules[:2]
        ) or "Rules not yet readable"
        tags = [
            *[str(rule.get("categoryLabel", "")).lower() for rule in rules],
            str(card.get("track", "cashback")),
        ]
        if not card.get("annualFee"):
            tags.append("no annual fee")
        rows.append({
            "name": card["name"],
            "network": card.get("network", "Unknown"),
            "headlineRate": headline,
            "annualFee": card.get("annualFee", 0),
            "track": card.get("track", "cashback"),
            "held": True,
            "deltaVsWallet": 0,
            **({"deltaNote": card["parseNote"]} if card.get("parseNote") else {}),
            "tags": list(dict.fromkeys(tag for tag in tags if tag)),
        })
    return rows


class Orchestrator:
    """Runs independent stages through persisted state; projection is the only UI-shape owner."""
    def __init__(self, store):
        self.store = store
        runtime = GeminiRuntime()
        self.ingestion = IngestionAgent()
        self.forecast = ForecastAgent()
        self.strategy = StrategyAgent()
        self.advisory = AdvisoryAgent(runtime)
        self.cardintel = CardIntelligenceAgent(runtime)

    def run(
        self,
        uid,
        request="Run CardSense",
        *,
        refresh_advice=True,
        refresh_card_intelligence=True,
        run_id=None,
    ):
        started, run_id = self._now(), run_id or uuid.uuid4().hex
        transactions = self.store.get_subcollection(uid, "transactions")
        planned = self.store.get_subcollection(uid, "planned")
        wallet = self.store.get_wallet(uid)

        # The feed has already been normalized at its cursor boundary. Start
        # every run by auditing that canonical input before downstream agents
        # consume it, so coverage failures appear in the correct stage/order.
        stage_started = perf_counter()
        self._start_stage(uid, run_id, "ingestion", "Ingestion", "transactions", ["plaid_items"])
        ingest = self.ingestion.run(uid, self.store)
        self._log(
            uid, run_id, "ingestion", "Ingestion", "transactions", ["plaid_items"],
            self.ingestion.degraded(ingest),
            round((perf_counter() - stage_started) * 1000),
            summary=(
                f"{ingest['purchases']} posted purchases from {ingest['total']} transactions; "
                f"{ingest['mccCoverage']:.0%} carry a merchant category code."
            ),
        )

        # Card intelligence runs before pricing: any card whose recheck
        # date has passed is reread before the optimiser prices anything, so a
        # rate change propagates without anyone noticing manually.
        stage_started = perf_counter()
        self._start_stage(uid, run_id, "card-intelligence", "Card intelligence", "card_rules", ["wallet"])
        if refresh_card_intelligence:
            wallet, reread, card_notes = self._recheck_due(uid, wallet)
            card_summary = f"Reread {reread} of {len(wallet)} cards." if reread else "No cards were due a recheck."
        else:
            reread, card_notes = 0, []
            card_summary = "Existing card rules retained during a deterministic account update."
        self._log(uid, run_id, "card-intelligence", "Card intelligence", "card_rules", ["wallet"],
                  card_notes, round((perf_counter() - stage_started) * 1000),
                  summary=card_summary)

        rules = {card["cardId"]: (self.store.get_global_doc("card_rules", card["cardId"]) or {}).get("rules", []) for card in wallet}
        stage_started = perf_counter()
        self._start_stage(uid, run_id, "strategy", "Simulation & strategy", "strategy_runs", ["transactions", "card_rules", "goal"])
        strategy = self.strategy.run(transactions, wallet, rules, self.store.get_user(uid).get("goal"))
        strategy["goal"] = self.strategy.goal_projection(self.store.get_user(uid).get("goal"), strategy["captured"])
        self.store.set_subdoc(uid, "strategy_runs", run_id, strategy)
        self._log(uid, run_id, "strategy", "Simulation & strategy", "strategy_runs", ["transactions", "card_rules", "goal"], strategy.get("degraded"), round((perf_counter() - stage_started) * 1000))

        stage_started = perf_counter()
        self._start_stage(uid, run_id, "forecast", "Forecast", "forecasts", ["transactions", "planned", "card_rules", "strategy_runs"])
        forecast = self.forecast.run(
            transactions,
            planned,
            wallet,
            rules,
            leakage_rate=self._leakage_rate(transactions, strategy.get("unclaimed", 0)),
        )
        self.store.set_subdoc(uid, "forecasts", run_id, forecast)
        self._log(
            uid, run_id, "forecast", "Forecast", "forecasts",
            ["transactions", "planned", "card_rules", "strategy_runs"],
            self.forecast.degraded(forecast),
            round((perf_counter() - stage_started) * 1000),
            summary=(
                f"Projected {forecast['projectedSpend']:.2f} over {forecast['horizonDays']} days "
                f"from {forecast['historyDays']} days of history and {forecast['plannedSpend']:.2f} declared spend."
            ),
        )
        if refresh_advice:
            stage_started = perf_counter()
            self._start_stage(uid, run_id, "advisory", "Advisory", "advice", ["strategy_runs", "forecasts"])
            advice = self.advisory.run(strategy, forecast, wallet)
            for item in advice:
                item["impact"] = _numeric_advice_value(item.get("impact"))
                item.setdefault("outcome", "open")
                item.setdefault("pushedAt", self._now())
                item.setdefault("predicted", item["impact"])
                item.setdefault("window", item["impactWindow"])
                self.store.set_subdoc(uid, "advice", item["id"], item)
            self._log(uid, run_id, "advisory", "Advisory", "advice", ["strategy_runs", "advice"], duration_ms=round((perf_counter() - stage_started) * 1000))
        else:
            self._start_stage(uid, run_id, "advisory", "Advisory", [], ["advice"])
            self._log(
                uid,
                run_id,
                "advisory",
                "Advisory",
                [],
                ["advice"],
                summary="Existing advice retained; deterministic state recalculated without a model call.",
            )
        snapshot = self.project(uid, run_id)
        self.store.set_snapshot(uid, snapshot)
        self.store.set_user(uid, {"lastRunId": run_id, "lastRunAt": snapshot["generatedAt"]})
        return run_id, snapshot

    def queue_run(self, uid, run_id):
        """Persist a visible run before background execution begins."""
        queued_at = self._now()
        for agent, label in AGENTS:
            self.store.write_agent_run(uid, f"{run_id}-{agent}", {
                "id": f"{run_id}-{agent}",
                "runId": run_id,
                "agent": agent,
                "label": label,
                "status": "queued",
                "startedAt": queued_at,
                "durationMs": 0,
                "summary": f"{label} queued.",
                "detail": None,
                "writes": [],
                "reads": [],
                "retryable": False,
            })

    def empty_snapshot(self, uid):
        """Return a contract-valid initial read model without running agents."""
        return self.project(uid, "initial")

    def project_planned_change(self, uid, *, added=None, removed_id=None):
        """Reproject persisted plans without rerunning the full agent pipeline."""
        snapshot = self.store.get_snapshot(uid) or self.empty_snapshot(uid)
        # The endpoint persists the mutation first. Reading the collection back
        # makes this projection authoritative even when the previous snapshot
        # was stale or another planned item was written between page loads.
        planned = self.store.get_subcollection(uid, "planned")
        planned.sort(key=lambda item: str(item.get("startDate", "")))

        transactions = self.store.get_subcollection(uid, "transactions")
        wallet = self.store.get_wallet(uid)
        rules = self._rules(wallet)
        snapshot["generatedAt"] = self._now()
        snapshot["planned"] = planned
        snapshot["totals"] = {
            **transaction_totals(transactions),
            "captured": float(snapshot.get("totals", {}).get("captured", 0)),
            "unclaimed": float(snapshot.get("totals", {}).get("unclaimed", 0)),
        }
        snapshot["forecast"] = self.forecast.run(
            transactions,
            planned,
            wallet,
            rules,
            leakage_rate=self._snapshot_leakage_rate(snapshot),
        )
        snapshot["cards"] = self.forecast.project_cards(transactions, wallet, rules)
        snapshot["readModelVersion"] = READ_MODEL_VERSION
        projected = Snapshot.model_validate(snapshot).model_dump(mode="json")
        self.store.set_snapshot(uid, projected)
        return projected

    def refresh_forecast_projection(self, uid, snapshot):
        """Upgrade an existing read model without running Gemini or all agents."""
        transactions = self.store.get_subcollection(uid, "transactions")
        planned = self.store.get_subcollection(uid, "planned")
        wallet = self.store.get_wallet(uid)
        rules = self._rules(wallet)
        snapshot["generatedAt"] = self._now()
        snapshot["readModelVersion"] = READ_MODEL_VERSION
        snapshot["planned"] = planned
        snapshot["wallet"] = wallet
        snapshot["catalog"] = project_catalog(self.store, uid, wallet)
        snapshot["totals"] = {
            **transaction_totals(transactions),
            "captured": float(snapshot.get("totals", {}).get("captured", 0)),
            "unclaimed": float(snapshot.get("totals", {}).get("unclaimed", 0)),
        }
        snapshot["forecast"] = self.forecast.run(
            transactions,
            planned,
            wallet,
            rules,
            leakage_rate=self._snapshot_leakage_rate(snapshot),
        )
        snapshot["cards"] = self.forecast.project_cards(transactions, wallet, rules)
        projected = Snapshot.model_validate(snapshot).model_dump(mode="json")
        self.store.set_snapshot(uid, projected)
        return projected

    def project_goal_change(self, uid, goal):
        """Patch a goal projection using the captured value already in the snapshot."""
        snapshot = self.store.get_snapshot(uid) or self.empty_snapshot(uid)
        captured = float(snapshot.get("totals", {}).get("captured", 0))
        projected_goal = self.strategy.goal_projection(goal, captured) if goal else None

        snapshot["generatedAt"] = self._now()
        snapshot["goal"] = projected_goal
        snapshot["trackPreference"] = goal["track"] if goal else None
        snapshot["recommendedTrack"] = goal["track"] if goal else "cashback"
        snapshot["trackRationale"] = (
            "Optimised against your stated goal."
            if goal else
            "Cash back is the stated nominal-value baseline."
        )
        projected = Snapshot.model_validate(snapshot).model_dump(mode="json")
        self.store.set_snapshot(uid, projected)
        return projected

    def project_advice_resolution(self, uid, advice):
        """Patch recommendation and track-record state without rerunning agents."""
        snapshot = self.store.get_snapshot(uid) or self.empty_snapshot(uid)
        advice_id = advice["id"]
        recommendations = [
            item for item in snapshot.get("recommendations", [])
            if item.get("id") != advice_id
        ]
        if advice.get("outcome") == "open":
            recommendations.append(self._recommendation(advice))

        records = [
            item for item in snapshot.get("trackRecord", {}).get("records", [])
            if item.get("id") != advice_id
        ]
        records.append({
            key: value for key, value in advice.items()
            if key in {"id", "outcome", "pushedAt", "resolvedAt", "headline", "card", "predicted", "actual", "window", "gapReason"}
        })

        snapshot["generatedAt"] = self._now()
        snapshot["recommendations"] = recommendations
        snapshot["trackRecord"] = self._track_record(records)
        projected = Snapshot.model_validate(snapshot).model_dump(mode="json")
        self.store.set_snapshot(uid, projected)
        return projected

    def forecast_for(self, uid, horizon_months: int = 1) -> dict:
        """Re-project spending over a different horizon, and nothing else.

        Changing the horizon is a question about arithmetic already-held data
        can answer. Routing it through a full run would re-invoke Gemini and
        re-extract card terms to produce a number that depends on neither.
        """
        transactions = self.store.get_subcollection(uid, "transactions")
        planned = self.store.get_subcollection(uid, "planned")
        wallet = self.store.get_wallet(uid)
        snapshot = self.store.get_snapshot(uid) or {}
        return self.forecast.run(
            transactions,
            planned,
            wallet,
            self._rules(wallet),
            leakage_rate=self._snapshot_leakage_rate(snapshot),
            horizon_months=horizon_months,
        )

    def project(self, uid, run_id):
        now = self._now()
        transactions = self.store.get_subcollection(uid, "transactions")
        planned = self.store.get_subcollection(uid, "planned")
        wallet = self.store.get_wallet(uid)
        strategy = self.store.get_subdoc(uid, "strategy_runs", run_id) or {"categories": [], "captured": 0, "unclaimed": 0, "goal": None}
        rules = self._rules(wallet)
        forecast = self.store.get_subdoc(uid, "forecasts", run_id) or self.forecast.run(
            transactions,
            planned,
            wallet,
            rules,
            leakage_rate=self._leakage_rate(transactions, strategy.get("unclaimed", 0)),
        )
        advice = self.store.get_subcollection(uid, "advice")
        activity = sorted(self.store.get_subcollection(uid, "agent_runs"), key=lambda item: item.get("startedAt", ""))[-50:]
        latest = {entry["agent"]: entry for entry in activity if entry.get("runId") == run_id}
        agents = [{"id": ident, "label": label, "status": latest.get(ident, {}).get("status", "ok"), "lastRunAt": latest.get(ident, {}).get("startedAt", now), **({"note": latest[ident]["detail"]} if latest.get(ident, {}).get("detail") else {})} for ident, label in AGENTS]
        cards = self.forecast.project_cards(transactions, wallet, rules)
        captured = strategy["captured"]
        goal = strategy.get("goal")
        preferred = goal.get("track") if goal else None
        track = preferred or "cashback"
        record = self._track_record(advice)
        totals = {
            **transaction_totals(transactions),
            "captured": captured,
            "unclaimed": strategy["unclaimed"],
        }
        data = {"readModelVersion": READ_MODEL_VERSION, "generatedAt": now, "period": {"label": "Current period", "start": str(date.today().replace(day=1)), "end": str(date.today())}, "totals": totals, "agents": agents, "recommendations": [self._recommendation(item) for item in advice if item.get("outcome") == "open"], "categories": strategy["categories"], "cards": cards, "tracks": [{"track": name, "rawUnits": round(captured / value, 2) if value else 0, "unitLabel": "dollars" if name == "cashback" else name, "rate": value, "nominal": captured, "source": f"{name.title()} nominal value assumption."} for name, value in VALUATIONS.items()], "trackPreference": preferred, "recommendedTrack": track, "trackRationale": "Optimised against your stated goal." if preferred else "Cash back is the stated nominal-value baseline.", "forecast": forecast, "goal": goal, "planned": planned, "trackRecord": record, "wallet": wallet, "catalog": project_catalog(self.store, uid, wallet), "activity": activity, "collections": [{"collection": "transactions", "writtenBy": "ingestion", "readBy": ["forecast", "strategy"]}, {"collection": "card_rules", "writtenBy": "card-intelligence", "readBy": ["forecast", "strategy"]}, {"collection": "forecasts", "writtenBy": "forecast", "readBy": ["advisory"]}, {"collection": "strategy_runs", "writtenBy": "strategy", "readBy": ["forecast", "advisory"]}, {"collection": "advice", "writtenBy": "advisory", "readBy": []}]}
        return Snapshot.model_validate(data).model_dump(mode="json")

    def _recheck_due(self, uid, wallet):
        """Reread the terms of any card whose recheck date has arrived.

        Only cards with a stored terms link are touched: rates entered by hand
        are the user's, and the agent must not overwrite them.
        """
        reread, notes, updated = 0, [], []
        for card in wallet:
            due = self.cardintel.due_for_recheck(card)
            if not due or not card.get("termsUrl"):
                updated.append(card)
                if card.get("parseStatus") != "parsed" and card.get("parseNote"):
                    notes.append(card["parseNote"])
                continue

            previous = self.store.get_global_doc("card_rules", card["cardId"])
            parsed = self.cardintel.parse({**card, "rules": None}, previous)
            reread += 1
            refreshed = {
                **card,
                "rules": parsed.get("rules", []),
                "characteristics": parsed.get("characteristics", {}),
                "source": parsed["source"],
                "recheckCadence": parsed.get("recheckCadence", "weekly"),
                "nextRecheckAt": parsed.get("nextRecheckAt"),
                "parseStatus": parsed.get("status", "failed"),
                "parseNote": parsed.get("note"),
                "parseConfidence": parsed.get("confidence", 0.0),
                "failureReason": parsed.get("failureReason"),
            }
            self.store.set_global_doc("card_rules", card["cardId"], {
                "rules": parsed.get("rules", []),
                "characteristics": parsed.get("characteristics", {}),
                "source": parsed["source"],
                "status": refreshed["parseStatus"],
                "confidence": refreshed["parseConfidence"],
            })
            self.store.set_subdoc(uid, "wallet", card["cardId"], refreshed)
            if refreshed["parseStatus"] != "parsed" and refreshed.get("parseNote"):
                notes.append(f"{card['name']}: {refreshed['parseNote']}")
            updated.append(refreshed)
        return updated, reread, notes

    def _summary(self, transactions):
        categories, monthly = {}, {}
        for tx in transactions:
            if not is_eligible_purchase(tx):
                continue
            category, amount = tx.get("category", "uncategorized"), float(tx.get("amount", 0))
            categories[category] = categories.get(category, 0) + amount
            if tx.get("date"):
                month = str(tx["date"])[:7]; monthly[month] = monthly.get(month, 0) + amount
        return {"spend": sum(categories.values()), "categories": categories, "monthly": monthly}

    def _rules(self, wallet):
        return {
            card["cardId"]: (
                self.store.get_global_doc("card_rules", card["cardId"]) or {}
            ).get("rules", [])
            for card in wallet
        }

    def _leakage_rate(self, transactions, unclaimed) -> float:
        spend = sum(
            float(transaction.get("amount", 0))
            for transaction in transactions
            if is_eligible_purchase(transaction)
        )
        if spend <= 0:
            return 0.0
        return min(1.0, max(0.0, float(unclaimed or 0) / spend))

    def _snapshot_leakage_rate(self, snapshot) -> float:
        totals = snapshot.get("totals") or {}
        # Leakage was originally calculated against signed (net) spend. Keep
        # that behaviour now that `spend` explicitly means gross purchases.
        spend = float(totals.get("netSpend", totals.get("spend")) or 0)
        if spend <= 0:
            return 0.0
        return min(1.0, max(0.0, float(totals.get("unclaimed") or 0) / spend))

    def _start_stage(self, uid, run_id, agent, label, writes, reads):
        self.store.write_agent_run(uid, f"{run_id}-{agent}", {
            "id": f"{run_id}-{agent}",
            "runId": run_id,
            "agent": agent,
            "label": label,
            "status": "running",
            "startedAt": self._now(),
            "durationMs": 0,
            "summary": f"{label} is running.",
            "detail": None,
            "writes": writes,
            "reads": reads,
            "retryable": False,
        })

    def _log(self, uid, run_id, agent, label, writes, reads, degraded=None, duration_ms=0, summary=None):
        detail = "; ".join(degraded or []) or None
        self.store.write_agent_run(uid, f"{run_id}-{agent}", {"id": f"{run_id}-{agent}", "runId": run_id, "agent": agent, "status": "degraded" if detail else "ok", "startedAt": self._now(), "durationMs": duration_ms, "summary": summary or f"{label} completed.", "detail": detail, "writes": writes, "reads": reads, "retryable": agent == "card-intelligence" and bool(detail)})

    def _track_record(self, advice):
        acted = [a for a in advice if a.get("outcome") == "acted"]
        records = []
        for item in advice:
            record = {key: value for key, value in item.items() if key in {"id", "outcome", "pushedAt", "resolvedAt", "headline", "card", "predicted", "actual", "window", "gapReason"}}
            record["predicted"] = _numeric_advice_value(item.get("predicted"))
            if "actual" in record:
                record["actual"] = _numeric_advice_value(record["actual"])
            records.append(record)
        return {"taken": len(acted), "offered": len(advice), "earned": round(sum(_numeric_advice_value(a.get("actual")) for a in acted), 2), "missed": round(sum(_numeric_advice_value(a.get("predicted")) for a in advice if a.get("outcome") in {"dismissed", "expired"}), 2), "accuracyNote": "Actual earnings are recorded after recommendation windows close.", "records": records}

    def _recommendation(self, item):
        recommendation = {key: value for key, value in item.items() if key in {"id", "urgency", "headline", "card", "tiedWith", "impact", "impactWindow", "deadline", "body", "trace"}}
        recommendation["impact"] = _numeric_advice_value(item.get("impact"))
        return recommendation

    def _now(self): return datetime.now(timezone.utc).isoformat()
