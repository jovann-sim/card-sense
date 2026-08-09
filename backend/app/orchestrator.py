from __future__ import annotations

from datetime import date, datetime, timezone
import uuid
from time import perf_counter

from .agents.advisory import AdvisoryAgent
from .agents.card_intelligence import CardIntelligenceAgent
from .agents.forecast import ForecastAgent
from .agents.runtime import GeminiRuntime
from .agents.strategy import StrategyAgent, VALUATIONS
from .models import Snapshot


AGENTS = [
    ("ingestion", "Ingestion"), ("forecast", "Forecast"),
    ("card-intelligence", "Card intelligence"), ("strategy", "Simulation & strategy"),
    ("advisory", "Advisory"),
]


class Orchestrator:
    """Runs independent stages through persisted state; projection is the only UI-shape owner."""
    def __init__(self, store):
        self.store = store
        runtime = GeminiRuntime()
        self.forecast = ForecastAgent()
        self.strategy = StrategyAgent()
        self.advisory = AdvisoryAgent(runtime)
        self.cardintel = CardIntelligenceAgent(runtime)

    def run(self, uid, request="Run CardSense"):
        started, run_id = self._now(), uuid.uuid4().hex
        transactions = self.store.get_subcollection(uid, "transactions")
        planned = self.store.get_subcollection(uid, "planned")
        wallet = self.store.get_wallet(uid)
        rules = {card["cardId"]: (self.store.get_global_doc("card_rules", card["cardId"]) or {}).get("rules", []) for card in wallet}
        summary = self._summary(transactions)
        stage_started = perf_counter()
        forecast = self.forecast.run(summary, planned)
        self.store.set_subdoc(uid, "forecasts", run_id, forecast)
        self._log(uid, run_id, "forecast", "Forecast", "forecasts", ["transactions", "planned", "card_rules"], duration_ms=round((perf_counter() - stage_started) * 1000))
        stage_started = perf_counter()
        strategy = self.strategy.run(transactions, wallet, rules, self.store.get_user(uid).get("goal"))
        strategy["goal"] = self.strategy.goal_projection(self.store.get_user(uid).get("goal"), strategy["captured"])
        self.store.set_subdoc(uid, "strategy_runs", run_id, strategy)
        self._log(uid, run_id, "strategy", "Simulation & strategy", "strategy_runs", ["transactions", "card_rules", "forecasts", "goal"], strategy.get("degraded"), round((perf_counter() - stage_started) * 1000))
        stage_started = perf_counter()
        advice = self.advisory.run(strategy, forecast, wallet)
        for item in advice:
            item.setdefault("outcome", "open")
            item.setdefault("pushedAt", self._now())
            item.setdefault("predicted", item["impact"])
            item.setdefault("window", item["impactWindow"])
            self.store.set_subdoc(uid, "advice", item["id"], item)
        self._log(uid, run_id, "advisory", "Advisory", "advice", ["strategy_runs", "advice"], duration_ms=round((perf_counter() - stage_started) * 1000))
        self._log(uid, run_id, "ingestion", "Ingestion", "transactions", ["plaid_items", "mcc_map"])
        card_notes = [c.get("parseNote") for c in wallet if c.get("parseStatus") != "parsed" and c.get("parseNote")]
        self._log(uid, run_id, "card-intelligence", "Card intelligence", "card_rules", ["wallet"], card_notes)
        snapshot = self.project(uid, run_id)
        self.store.set_snapshot(uid, snapshot)
        self.store.set_user(uid, {"lastRunId": run_id, "lastRunAt": snapshot["generatedAt"]})
        return run_id, snapshot

    def empty_snapshot(self, uid):
        """Return a contract-valid initial read model without running agents."""
        return self.project(uid, "initial")

    def project(self, uid, run_id):
        now = self._now()
        transactions = self.store.get_subcollection(uid, "transactions")
        planned = self.store.get_subcollection(uid, "planned")
        wallet = self.store.get_wallet(uid)
        forecast = self.store.get_subdoc(uid, "forecasts", run_id) or self.forecast.run(self._summary(transactions), planned)
        strategy = self.store.get_subdoc(uid, "strategy_runs", run_id) or {"categories": [], "captured": 0, "unclaimed": 0, "goal": None}
        advice = self.store.get_subcollection(uid, "advice")
        activity = sorted(self.store.get_subcollection(uid, "agent_runs"), key=lambda item: item.get("startedAt", ""))[-50:]
        latest = {entry["agent"]: entry for entry in activity if entry.get("runId") == run_id}
        agents = [{"id": ident, "label": label, "status": latest.get(ident, {}).get("status", "ok"), "lastRunAt": latest.get(ident, {}).get("startedAt", now), **({"note": latest[ident]["detail"]} if latest.get(ident, {}).get("detail") else {})} for ident, label in AGENTS]
        cards = []
        for card in wallet:
            rules = (self.store.get_global_doc("card_rules", card["cardId"]) or {}).get("rules", [])
            first = rules[0] if rules else {}
            cards.append({"name": card["name"], "last4": card["last4"], "network": card["network"], "categoryLabel": first.get("categoryLabel", "Unverified"), "rate": first.get("rate", "—"), "cycleSpend": 0, "cap": first.get("cap"), "cycleLabel": first.get("cycleLabel", "no cap"), "state": "unverified" if card.get("parseStatus") != "parsed" else "healthy", **({"note": card["parseNote"]} if card.get("parseNote") else {})})
        captured = strategy["captured"]
        goal = strategy.get("goal")
        preferred = goal.get("track") if goal else None
        track = preferred or "cashback"
        record = self._track_record(advice)
        data = {"generatedAt": now, "period": {"label": "Current period", "start": str(date.today().replace(day=1)), "end": str(date.today())}, "totals": {"spend": round(sum(float(t.get("amount", 0)) for t in transactions), 2), "captured": captured, "unclaimed": strategy["unclaimed"]}, "agents": agents, "recommendations": [self._recommendation(item) for item in advice if item.get("outcome") == "open"], "categories": strategy["categories"], "cards": cards, "tracks": [{"track": name, "rawUnits": round(captured / value, 2) if value else 0, "unitLabel": "dollars" if name == "cashback" else name, "rate": value, "nominal": captured, "source": f"{name.title()} nominal value assumption."} for name, value in VALUATIONS.items()], "trackPreference": preferred, "recommendedTrack": track, "trackRationale": "Optimised against your stated goal." if preferred else "Cash back is the stated nominal-value baseline.", "forecast": forecast, "goal": goal, "planned": planned, "trackRecord": record, "wallet": wallet, "catalog": self.store.get_subcollection(uid, "catalog"), "activity": activity, "collections": [{"collection": "transactions", "writtenBy": "ingestion", "readBy": ["forecast", "strategy"]}, {"collection": "card_rules", "writtenBy": "card-intelligence", "readBy": ["forecast", "strategy"]}, {"collection": "forecasts", "writtenBy": "forecast", "readBy": ["strategy"]}, {"collection": "strategy_runs", "writtenBy": "strategy", "readBy": ["advisory"]}, {"collection": "advice", "writtenBy": "advisory", "readBy": []}]}
        return Snapshot.model_validate(data).model_dump(mode="json")

    def _summary(self, transactions):
        categories, monthly = {}, {}
        for tx in transactions:
            category, amount = tx.get("category", "uncategorized"), float(tx.get("amount", 0))
            categories[category] = categories.get(category, 0) + amount
            if tx.get("date"):
                month = str(tx["date"])[:7]; monthly[month] = monthly.get(month, 0) + amount
        return {"spend": sum(categories.values()), "categories": categories, "monthly": monthly}

    def _log(self, uid, run_id, agent, label, writes, reads, degraded=None, duration_ms=0):
        detail = "; ".join(degraded or []) or None
        self.store.write_agent_run(uid, f"{run_id}-{agent}", {"id": f"{run_id}-{agent}", "runId": run_id, "agent": agent, "status": "degraded" if detail else "ok", "startedAt": self._now(), "durationMs": duration_ms, "summary": f"{label} completed.", "detail": detail, "writes": writes, "reads": reads, "retryable": False})

    def _track_record(self, advice):
        acted = [a for a in advice if a.get("outcome") == "acted"]
        return {"taken": len(acted), "offered": len(advice), "earned": round(sum(float(a.get("actual", 0)) for a in acted), 2), "missed": round(sum(float(a.get("predicted", 0)) for a in advice if a.get("outcome") in {"dismissed", "expired"}), 2), "accuracyNote": "Actual earnings are recorded after recommendation windows close.", "records": [{key: value for key, value in item.items() if key in {"id", "outcome", "pushedAt", "resolvedAt", "headline", "card", "predicted", "actual", "window", "gapReason"}} for item in advice]}

    def _recommendation(self, item):
        return {key: value for key, value in item.items() if key in {"id", "urgency", "headline", "card", "tiedWith", "impact", "impactWindow", "deadline", "body", "trace"}}

    def _now(self): return datetime.now(timezone.utc).isoformat()
