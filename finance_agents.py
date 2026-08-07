from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import csv
import os
from pathlib import Path
import re
from typing import Any

from google import genai


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def _parse_amount(value: str | None) -> float:
    if value is None:
        return 0.0
    cleaned = value.strip().replace(",", "")
    if not cleaned:
        return 0.0
    cleaned = cleaned.replace("$", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None

    cleaned = value.strip()
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(cleaned, pattern).date()
        except ValueError:
            continue
    return None


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _json_default(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _json_dump(value: Any) -> str:
    return json.dumps(value, default=_json_default, indent=2, sort_keys=True)


class VertexAgentRuntime:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("FINANCE_AGENT_MODEL", "gemini-2.5-flash")
        self.client = None
        self.error: str | None = None
        try:
            self.client = genai.Client(vertexai=True, location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"))
        except Exception as exc:
            self.error = str(exc)

    @property
    def status(self) -> str:
        if self.client is None:
            return f"fallback: {self.error}" if self.error else "fallback"
        return "vertex"

    def generate_json(self, system_prompt: str, user_payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        if self.client is None:
            return fallback

        prompt = (
            f"{system_prompt}\n\n"
            "Return valid JSON only. Do not wrap the response in markdown fences.\n\n"
            f"INPUT:\n{_json_dump(user_payload)}"
        )
        try:
            response = self.client.models.generate_content(model=self.model, contents=prompt)
            text = _strip_code_fences(response.text or "")
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return fallback


@dataclass(frozen=True)
class TransactionRecord:
    source_file: str
    posted_date: date | None
    amount: float
    category: str
    merchant: str
    description: str


@dataclass
class SpendingSummary:
    total_spend: float
    transaction_count: int
    category_totals: dict[str, float] = field(default_factory=dict)
    monthly_totals: dict[str, float] = field(default_factory=dict)
    source_files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CardProfile:
    name: str
    base_rate: float
    bonus_rates: dict[str, float] = field(default_factory=dict)
    monthly_cap: float | None = None


@dataclass
class RewardResult:
    best_card: str
    best_value: float
    rankings: list[dict[str, Any]] = field(default_factory=list)
    reminders: list[str] = field(default_factory=list)


@dataclass
class BudgetForecast:
    projected_monthly_spend: float
    recommended_cap: float | None
    trend: str
    notes: list[str] = field(default_factory=list)


@dataclass
class DealSignal:
    active_watchlist: list[str] = field(default_factory=list)
    summary: str = "Deal monitoring is scaffolded and ready for a live data source."


@dataclass
class RecommendationResult:
    habits: list[str] = field(default_factory=list)
    card_recommendation: str = ""
    reminders: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class StageResult:
    agent: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    request: str
    stages: list[StageResult]
    final_recommendation: RecommendationResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "stages": [asdict(stage) for stage in self.stages],
            "final_recommendation": asdict(self.final_recommendation),
        }

    def render(self) -> str:
        lines = [f"Request: {self.request}", ""]
        for stage in self.stages:
            lines.append(f"[{stage.agent}] {stage.summary}")
            for key, value in stage.details.items():
                lines.append(f"  - {key}: {value}")
            lines.append("")

        lines.append("[recommendation] " + self.final_recommendation.summary)
        for habit in self.final_recommendation.habits:
            lines.append(f"  - habit: {habit}")
        if self.final_recommendation.card_recommendation:
            lines.append(f"  - card: {self.final_recommendation.card_recommendation}")
        for reminder in self.final_recommendation.reminders:
            lines.append(f"  - reminder: {reminder}")
        return "\n".join(lines)


class TransactionAgent:
    name = "transaction"

    def __init__(self, runtime: VertexAgentRuntime) -> None:
        self.runtime = runtime

    def discover_csv_files(self, statement_dir: Path) -> list[Path]:
        if not statement_dir.exists():
            return []
        return sorted(path for path in statement_dir.glob("*.csv") if path.is_file())

    def load_transactions(self, csv_files: list[Path]) -> list[TransactionRecord]:
        transactions: list[TransactionRecord] = []
        for csv_file in csv_files:
            with csv_file.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                field_map = {_normalize(name): name for name in (reader.fieldnames or [])}
                for row in reader:
                    amount = self._extract_amount(row, field_map)
                    if amount <= 0:
                        continue
                    transactions.append(
                        TransactionRecord(
                            source_file=csv_file.name,
                            posted_date=self._extract_date(row, field_map),
                            amount=amount,
                            category=self._extract_text(row, field_map, ("category", "type", "group"), default="uncategorized"),
                            merchant=self._extract_text(row, field_map, ("merchant", "payee", "name", "description"), default="unknown"),
                            description=self._extract_text(row, field_map, ("description", "memo", "details"), default=""),
                        )
                    )
        return transactions

    def summarize_spending(self, transactions: list[TransactionRecord], csv_files: list[Path]) -> SpendingSummary:
        category_totals: dict[str, float] = defaultdict(float)
        monthly_totals: dict[str, float] = defaultdict(float)
        total_spend = 0.0

        for transaction in transactions:
            total_spend += transaction.amount
            category_key = _normalize(transaction.category) or "uncategorized"
            category_totals[category_key] += transaction.amount
            if transaction.posted_date is not None:
                month_key = transaction.posted_date.strftime("%Y-%m")
                monthly_totals[month_key] += transaction.amount

        notes = []
        if not csv_files:
            notes.append("No bank statement CSV files were found.")
        elif not transactions:
            notes.append("CSV files were found, but no spend rows could be parsed from the detected columns.")

        return SpendingSummary(
            total_spend=round(total_spend, 2),
            transaction_count=len(transactions),
            category_totals=dict(sorted(category_totals.items(), key=lambda item: item[1], reverse=True)),
            monthly_totals=dict(sorted(monthly_totals.items())),
            source_files=[csv_file.name for csv_file in csv_files],
            notes=notes,
        )

    def run(self, request: str, statement_dir: Path) -> tuple[list[TransactionRecord], SpendingSummary, str]:
        csv_files = self.discover_csv_files(statement_dir)
        transactions = self.load_transactions(csv_files)
        summary = self.summarize_spending(transactions, csv_files)
        model_result = self.runtime.generate_json(
            system_prompt=(
                "You are the transaction agent for a personal finance workflow. "
                "Analyze statement spend and summarize the most important spending patterns, risks, and missing-data caveats."
            ),
            user_payload={
                "request": request,
                "spending_summary": {
                    "total_spend": summary.total_spend,
                    "transaction_count": summary.transaction_count,
                    "category_totals": summary.category_totals,
                    "monthly_totals": summary.monthly_totals,
                    "source_files": summary.source_files,
                    "notes": summary.notes,
                },
                "sample_transactions": [
                    {
                        "source_file": transaction.source_file,
                        "posted_date": transaction.posted_date,
                        "amount": transaction.amount,
                        "category": transaction.category,
                        "merchant": transaction.merchant,
                    }
                    for transaction in transactions[:5]
                ],
            },
            fallback={
                "summary": "Retrieved bank statement CSVs and summarized spend.",
                "highlights": summary.notes,
                "notes": summary.notes,
            },
        )
        summary.notes = list(model_result.get("notes", summary.notes))
        summary.notes.extend(list(model_result.get("highlights", [])))
        summary.notes = list(dict.fromkeys(summary.notes))
        return transactions, summary, str(model_result.get("summary", "Retrieved bank statement CSVs and summarized spend."))

    def _extract_amount(self, row: dict[str, str], field_map: dict[str, str]) -> float:
        for candidate in ("amount", "transaction_amount", "debit", "withdrawal", "expense", "value"):
            field_name = field_map.get(candidate)
            if field_name is not None:
                parsed = _parse_amount(row.get(field_name))
                if parsed != 0.0:
                    return abs(parsed)

        credit_field = field_map.get("credit")
        if credit_field is not None:
            return 0.0

        return 0.0

    def _extract_date(self, row: dict[str, str], field_map: dict[str, str]) -> date | None:
        for candidate in ("date", "posted_date", "transaction_date", "trans_date"):
            field_name = field_map.get(candidate)
            if field_name is not None:
                return _parse_date(row.get(field_name))
        return None

    def _extract_text(
        self,
        row: dict[str, str],
        field_map: dict[str, str],
        candidates: tuple[str, ...],
        default: str,
    ) -> str:
        for candidate in candidates:
            field_name = field_map.get(candidate)
            if field_name is not None:
                value = (row.get(field_name) or "").strip()
                if value:
                    return value
        return default


class BudgetAgent:
    name = "budget"

    def __init__(self, runtime: VertexAgentRuntime) -> None:
        self.runtime = runtime

    def forecast(self, request: str, summary: SpendingSummary) -> BudgetForecast:
        if summary.monthly_totals:
            monthly_values = list(summary.monthly_totals.values())
            average_monthly = sum(monthly_values) / len(monthly_values)
            trend = "rising" if len(monthly_values) >= 2 and monthly_values[-1] > monthly_values[0] else "stable"
            projected = round(average_monthly * 1.05, 2)
            cap: float | None = round(projected * 0.9, 2)
        else:
            average_monthly = summary.total_spend
            trend = "insufficient data"
            projected = round(average_monthly, 2)
            cap = None
        notes = ["Budget forecast is based on the parsed statement summary."]
        if not summary.monthly_totals:
            notes.append("Monthly history was unavailable, so the forecast falls back to total spend.")

        model_result = self.runtime.generate_json(
            system_prompt=(
                "You are the budget agent. Forecast likely future monthly spend from the provided spend summary. "
                "Return projected_monthly_spend, recommended_cap, trend, and notes."
            ),
            user_payload={
                "request": request,
                "spending_summary": {
                    "total_spend": summary.total_spend,
                    "transaction_count": summary.transaction_count,
                    "category_totals": summary.category_totals,
                    "monthly_totals": summary.monthly_totals,
                },
            },
            fallback={
                "projected_monthly_spend": projected,
                "recommended_cap": cap,
                "trend": trend,
                "notes": notes,
            },
        )

        projected = float(model_result.get("projected_monthly_spend", projected))
        recommended_cap = model_result.get("recommended_cap", cap)
        if recommended_cap is not None:
            recommended_cap = float(recommended_cap)
        trend = str(model_result.get("trend", trend))
        notes = [str(note) for note in model_result.get("notes", notes)]

        return BudgetForecast(
            projected_monthly_spend=projected,
            recommended_cap=recommended_cap,
            trend=trend,
            notes=notes,
        )


class RewardsAgent:
    name = "rewards"

    def __init__(self, runtime: VertexAgentRuntime) -> None:
        self.runtime = runtime
        self.cards = [
            CardProfile(name="Everyday Cash", base_rate=0.01),
            CardProfile(name="Groceries Plus", base_rate=0.01, bonus_rates={"groceries": 0.03, "dining": 0.02}, monthly_cap=500.0),
            CardProfile(name="Travel Perks", base_rate=0.01, bonus_rates={"travel": 0.03, "entertainment": 0.02}, monthly_cap=1000.0),
        ]

    def calculate(self, request: str, summary: SpendingSummary) -> RewardResult:
        rankings: list[dict[str, Any]] = []
        reminders: list[str] = []

        for card in self.cards:
            estimated_value = self._estimate_card_value(summary, card)
            card_details = {
                "card": card.name,
                "estimated_reward_value": round(estimated_value, 2),
                "monthly_cap": card.monthly_cap,
            }
            rankings.append(card_details)
            if card.monthly_cap is not None and summary.total_spend >= card.monthly_cap:
                reminders.append(f"{card.name} rewards are likely at or near the monthly cap.")

        rankings.sort(key=lambda item: item["estimated_reward_value"], reverse=True)
        best = rankings[0] if rankings else {"card": "No card data", "estimated_reward_value": 0.0}
        if summary.total_spend == 0:
            best = {"card": "No card recommendation yet", "estimated_reward_value": 0.0}
            reminders.append("Add statement CSVs before optimizing card rewards.")
        elif best["estimated_reward_value"] > 0:
            reminders.append(f"Track {best['card']} rewards to avoid missing a max-out window.")

        model_result = self.runtime.generate_json(
            system_prompt=(
                "You are the rewards agent. Rank the provided cards against the spend summary and explain the best option. "
                "Return best_card, best_value, rankings, and reminders."
            ),
            user_payload={
                "request": request,
                "spending_summary": {
                    "total_spend": summary.total_spend,
                    "transaction_count": summary.transaction_count,
                    "category_totals": summary.category_totals,
                },
                "cards": [asdict(card) for card in self.cards],
            },
            fallback={
                "best_card": best["card"],
                "best_value": best["estimated_reward_value"],
                "rankings": rankings,
                "reminders": reminders,
            },
        )

        best_card = str(model_result.get("best_card", best["card"]))
        best_value = float(model_result.get("best_value", best["estimated_reward_value"]))
        rankings = list(model_result.get("rankings", rankings))
        reminders = [str(reminder) for reminder in model_result.get("reminders", reminders)]

        return RewardResult(
            best_card=best_card,
            best_value=best_value,
            rankings=rankings,
            reminders=reminders,
        )

    def _estimate_card_value(self, summary: SpendingSummary, card: CardProfile) -> float:
        total = summary.total_spend * card.base_rate
        for category, spend in summary.category_totals.items():
            applied_rate = card.base_rate + card.bonus_rates.get(category, 0.0)
            total += spend * max(applied_rate - card.base_rate, 0.0)
        return total


class DealAgent:
    name = "deal"

    def __init__(self, runtime: VertexAgentRuntime) -> None:
        self.runtime = runtime

    def monitor(self, request: str, summary: SpendingSummary) -> DealSignal:
        fallback = DealSignal(
            active_watchlist=["subscriptions", "groceries", "travel", "utilities"],
            summary="Deal monitoring is scaffolded; attach a web search or merchant feed next.",
        )

        model_result = self.runtime.generate_json(
            system_prompt=(
                "You are the deal agent. Suggest categories or merchant areas worth monitoring for better deals. "
                "Return active_watchlist and summary."
            ),
            user_payload={
                "request": request,
                "spending_summary": {
                    "total_spend": summary.total_spend,
                    "category_totals": summary.category_totals,
                },
                "baseline_watchlist": fallback.active_watchlist,
            },
            fallback={
                "active_watchlist": fallback.active_watchlist,
                "summary": fallback.summary,
            },
        )

        return DealSignal(
            active_watchlist=[str(item) for item in model_result.get("active_watchlist", fallback.active_watchlist)],
            summary=str(model_result.get("summary", fallback.summary)),
        )


class RecommendationAgent:
    name = "recommendation"

    def __init__(self, runtime: VertexAgentRuntime) -> None:
        self.runtime = runtime

    def synthesize(
        self,
        request: str,
        summary: SpendingSummary,
        budget: BudgetForecast,
        rewards: RewardResult,
        deal: DealSignal,
    ) -> RecommendationResult:
        habits: list[str] = []
        reminders: list[str] = []

        if summary.category_totals:
            top_category, top_spend = next(iter(summary.category_totals.items()))
            share = top_spend / summary.total_spend if summary.total_spend else 0.0
            if share >= 0.3:
                habits.append(f"Reduce concentration in {top_category}; it is {share:.0%} of spend.")

        if budget.recommended_cap is not None:
            habits.append(f"Use a monthly cap around {budget.recommended_cap:.2f} based on current spend patterns.")
        else:
            habits.append("Gather statement history before setting a monthly cap.")

        if rewards.best_card != "No card recommendation yet":
            habits.append(f"Prefer {rewards.best_card} for the current spend mix.")

        if deal.active_watchlist:
            habits.append(f"Keep deal alerts active for: {', '.join(deal.active_watchlist)}.")

        reminders.extend(rewards.reminders)
        if summary.total_spend == 0:
            reminders.append("No spend data was parsed, so recommendations are currently placeholder-only.")

        if rewards.best_value > 0 and budget.projected_monthly_spend > 0:
            summary_text = (
                f"Best card: {rewards.best_card}; projected monthly spend: {budget.projected_monthly_spend:.2f}; "
                f"deal monitoring: enabled for {len(deal.active_watchlist)} categories."
            )
        else:
            summary_text = "Recommendation workflow is in place, but it needs statement CSVs for full personalization."

        model_result = self.runtime.generate_json(
            system_prompt=(
                "You are the recommendation agent. Synthesize the transaction, budget, rewards, and deal outputs into spending habits, card guidance, and reminders. "
                "Return habits, card_recommendation, reminders, and summary."
            ),
            user_payload={
                "request": request,
                "spending_summary": {
                    "total_spend": summary.total_spend,
                    "transaction_count": summary.transaction_count,
                    "category_totals": summary.category_totals,
                    "monthly_totals": summary.monthly_totals,
                },
                "budget": asdict(budget),
                "rewards": asdict(rewards),
                "deal": asdict(deal),
            },
            fallback={
                "habits": habits,
                "card_recommendation": rewards.best_card,
                "reminders": reminders,
                "summary": summary_text,
            },
        )

        return RecommendationResult(
            habits=[str(item) for item in model_result.get("habits", habits)],
            card_recommendation=str(model_result.get("card_recommendation", rewards.best_card)),
            reminders=[str(item) for item in model_result.get("reminders", reminders)],
            summary=str(model_result.get("summary", summary_text)),
        )


class FinanceOrchestrator:
    def __init__(self) -> None:
        self.runtime = VertexAgentRuntime()
        self.transaction_agent = TransactionAgent(self.runtime)
        self.budget_agent = BudgetAgent(self.runtime)
        self.rewards_agent = RewardsAgent(self.runtime)
        self.deal_agent = DealAgent(self.runtime)
        self.recommendation_agent = RecommendationAgent(self.runtime)

    def run(self, request: str, statement_dir: Path) -> WorkflowResult:
        transactions, summary, transaction_summary = self.transaction_agent.run(request, statement_dir)
        budget = self.budget_agent.forecast(request, summary)
        rewards = self.rewards_agent.calculate(request, summary)
        deal = self.deal_agent.monitor(request, summary)
        recommendation = self.recommendation_agent.synthesize(request, summary, budget, rewards, deal)

        stages = [
            StageResult(
                agent=self.transaction_agent.name,
                summary=transaction_summary,
                details={
                    "csv_files": summary.source_files,
                    "transaction_count": summary.transaction_count,
                    "total_spend": summary.total_spend,
                    "category_totals": summary.category_totals,
                    "notes": summary.notes,
                    "vertex_model": self.runtime.model,
                    "vertex_status": self.runtime.status,
                },
            ),
            StageResult(
                agent=self.budget_agent.name,
                summary="Projected future spend from statement history.",
                details={
                    "projected_monthly_spend": budget.projected_monthly_spend,
                    "recommended_cap": budget.recommended_cap,
                    "trend": budget.trend,
                    "notes": budget.notes,
                    "vertex_model": self.runtime.model,
                    "vertex_status": self.runtime.status,
                },
            ),
            StageResult(
                agent=self.rewards_agent.name,
                summary="Ranked cards by estimated rewards value.",
                details={
                    "best_card": rewards.best_card,
                    "best_value": rewards.best_value,
                    "rankings": rewards.rankings,
                    "reminders": rewards.reminders,
                    "vertex_model": self.runtime.model,
                    "vertex_status": self.runtime.status,
                },
            ),
            StageResult(
                agent=self.deal_agent.name,
                summary=deal.summary,
                details={"active_watchlist": deal.active_watchlist, "vertex_model": self.runtime.model, "vertex_status": self.runtime.status},
            ),
        ]

        return WorkflowResult(request=request, stages=stages, final_recommendation=recommendation)