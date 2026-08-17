"""Run deterministic golden evaluations for all five CardSense agents.

Usage:

    cd backend
    .venv/bin/python -m evals.run_agent_evals
    .venv/bin/python -m evals.run_agent_evals --json

The suite does not call Plaid or Gemini. Model extraction quality has a
separate, opt-in corpus runner; this suite protects the stable agent contracts,
financial arithmetic, grounding, abstention, and recovery behavior in CI.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date
from time import perf_counter
from typing import Any

from app.agents.advisory import AdvisoryAgent, AdvisoryWordingOutput
from app.agents.card_intelligence import CardIntelligenceAgent
from app.agents.forecast import ForecastAgent
from app.agents.ingestion import IngestionAgent
from app.agents.runtime import ModelUnavailable
from app.agents.schema import ExtractionResult
from app.agents.strategy import StrategyAgent
from evals.golden_cases import CASES_BY_AGENT


@dataclass
class CaseResult:
    agent: str
    case: str
    risk: str
    passed: bool
    assertions_passed: int
    assertions_total: int
    duration_ms: float
    failures: list[str] = field(default_factory=list)
    unsupported_claims: int = 0


class StaticRuntime:
    """A deterministic substitute for model wording or structured extraction."""

    def __init__(self, output: Any = None, error: dict | None = None):
        self.output = output
        self.error = error

    def structured(self, _prompt, _schema, **_kwargs):
        if self.error:
            raise ModelUnavailable(self.error["reason"], self.error.get("detail", "golden failure"))
        return self.output


def _at(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, (list, tuple)):
            current = current[int(part)]
        else:
            current = current[part]
    return current


def _compare(result: Any, expected: dict[str, Any]) -> tuple[int, list[str]]:
    passed = 0
    failures = []
    for path, wanted in expected.items():
        try:
            actual = len(result) if path == "length" else _at(result, path)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            failures.append(f"{path}: missing ({exc})")
            continue
        if actual == wanted:
            passed += 1
        else:
            failures.append(f"{path}: expected {wanted!r}, got {actual!r}")
    return passed, failures


def _ingestion(case: dict) -> Any:
    agent = IngestionAgent()
    if case["operation"] == "normalise":
        return agent.normalise_plaid(deepcopy(case["input"]))
    summary = agent.summarise(
        deepcopy(case["input"]), linked_account_ids=set(case.get("linkedAccountIds", [])),
    )
    return {**summary, "degradedCount": len(agent.degraded(summary))}


def _card_intelligence(case: dict) -> Any:
    extraction = ExtractionResult.model_validate(case["extraction"]) if case.get("extraction") else None
    runtime = StaticRuntime(extraction, case.get("error"))
    # Recovery is intentionally exercised with a synthetic model failure. Keep
    # that expected warning out of human reports and JSON artifacts.
    logger = logging.getLogger("app.agents.card_intelligence")
    previous_level = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        return CardIntelligenceAgent(runtime).parse(
            deepcopy(case["card"]), deepcopy(case.get("previous")),
        )
    finally:
        logger.setLevel(previous_level)


def _strategy(case: dict) -> Any:
    return StrategyAgent().run(
        deepcopy(case["transactions"]), deepcopy(case["wallet"]), deepcopy(case["rules"]),
    )


def _forecast(case: dict) -> Any:
    return ForecastAgent().run(
        deepcopy(case["transactions"]),
        deepcopy(case["planned"]),
        deepcopy(case.get("wallet", [])),
        deepcopy(case.get("rules", {})),
        today=date.fromisoformat(case["today"]),
        leakage_rate=case.get("leakageRate", 0.0),
        horizon_months=case.get("horizonMonths", 1),
    )


def _advisory(case: dict) -> Any:
    wording = AdvisoryWordingOutput.model_validate(case.get("wording", {}))
    return AdvisoryAgent(StaticRuntime(wording)).run(
        deepcopy(case["strategy"]), deepcopy(case["forecast"]), deepcopy(case["wallet"]),
    )


RUNNERS = {
    "ingestion": _ingestion,
    "card-intelligence": _card_intelligence,
    "strategy": _strategy,
    "forecast": _forecast,
    "advisory": _advisory,
}


def _advisory_violations(case: dict, recommendations: list[dict]) -> list[str]:
    """Financial/card claims must be traceable to deterministic input facts."""
    wallet_names = {card["name"] for card in case["wallet"]}
    allowed_impacts = {float(value) for value in case.get("allowedImpacts", [])}
    violations = []
    for index, item in enumerate(recommendations):
        card = item.get("card")
        if card and card.get("name") not in wallet_names:
            violations.append(f"recommendation {index} names an unheld card")
        impact = float(item.get("impact") or 0)
        if impact not in allowed_impacts:
            violations.append(f"recommendation {index} has unsupported impact {impact:g}")
        text = f"{item.get('headline', '')} {item.get('body', '')}"
        for raw in re.findall(r"[$€£]\s*(\d+(?:\.\d+)?)", text):
            if float(raw) != impact:
                violations.append(f"recommendation {index} states unsupported amount {raw}")
    folded = " ".join(str(item) for item in recommendations).casefold()
    for forbidden in case.get("forbiddenText", []):
        if forbidden.casefold() in folded:
            violations.append(f"model-introduced text survived validation: {forbidden!r}")
    return violations


def evaluate_case(agent: str, case: dict) -> CaseResult:
    started = perf_counter()
    failures: list[str] = []
    unsupported = 0
    try:
        output = RUNNERS[agent](case)
        passed, failures = _compare(output, case["expect"])
        if agent == "advisory":
            grounding = _advisory_violations(case, output)
            unsupported = len(grounding)
            failures.extend(grounding)
        total = len(case["expect"]) + (1 if agent == "advisory" else 0)
        if agent == "advisory":
            passed += int(unsupported == 0)
    except Exception as exc:  # The report must identify a crashing case, not abort the suite.
        total = len(case["expect"]) + (1 if agent == "advisory" else 0)
        passed = 0
        failures = [f"raised {type(exc).__name__}: {exc}"]
    return CaseResult(
        agent=agent,
        case=case["id"],
        risk=case["risk"],
        passed=not failures,
        assertions_passed=passed,
        assertions_total=total,
        duration_ms=round((perf_counter() - started) * 1000, 3),
        failures=failures,
        unsupported_claims=unsupported,
    )


def run_suite(selected_agents: list[str] | None = None) -> dict:
    chosen = selected_agents or list(CASES_BY_AGENT)
    results = [
        evaluate_case(agent, case)
        for agent in chosen
        for case in CASES_BY_AGENT[agent]
    ]
    agents = {}
    for agent in chosen:
        rows = [row for row in results if row.agent == agent]
        agents[agent] = {
            "casesPassed": sum(row.passed for row in rows),
            "casesTotal": len(rows),
            "assertionsPassed": sum(row.assertions_passed for row in rows),
            "assertionsTotal": sum(row.assertions_total for row in rows),
            "durationMs": round(sum(row.duration_ms for row in rows), 3),
            "unsupportedClaims": sum(row.unsupported_claims for row in rows),
        }
    cases_passed = sum(row.passed for row in results)
    assertions_passed = sum(row.assertions_passed for row in results)
    assertions_total = sum(row.assertions_total for row in results)
    unsupported_claims = sum(row.unsupported_claims for row in results)
    return {
        "passed": cases_passed == len(results) and unsupported_claims == 0,
        "qualityGates": {
            "casePassRate": round(cases_passed / len(results), 4) if results else 0,
            "assertionPassRate": round(assertions_passed / assertions_total, 4) if assertions_total else 0,
            "unsupportedClaims": unsupported_claims,
        },
        "agents": agents,
        "cases": [asdict(row) for row in results],
    }


def _human(report: dict) -> str:
    lines = ["CardSense golden agent evaluations", ""]
    for agent, metrics in report["agents"].items():
        mark = "PASS" if metrics["casesPassed"] == metrics["casesTotal"] else "FAIL"
        lines.append(
            f"{mark:4}  {agent:18} "
            f"cases {metrics['casesPassed']}/{metrics['casesTotal']}  "
            f"assertions {metrics['assertionsPassed']}/{metrics['assertionsTotal']}  "
            f"{metrics['durationMs']:.3f} ms"
        )
    gates = report["qualityGates"]
    lines.extend([
        "",
        f"Case pass rate:      {gates['casePassRate']:.1%}",
        f"Assertion pass rate: {gates['assertionPassRate']:.1%}",
        f"Unsupported claims:  {gates['unsupportedClaims']}",
    ])
    failures = [case for case in report["cases"] if not case["passed"]]
    for case in failures:
        lines.append(f"\nFAIL {case['agent']}/{case['case']}")
        lines.extend(f"  - {failure}" for failure in case["failures"])
    lines.append("\nQUALITY GATES PASSED" if report["passed"] else "\nQUALITY GATES FAILED")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit the complete machine-readable report.")
    parser.add_argument(
        "--agent", action="append", choices=list(CASES_BY_AGENT),
        help="Evaluate only this agent; repeat to select more than one.",
    )
    args = parser.parse_args(argv)
    report = run_suite(args.agent)
    print(json.dumps(report, indent=2) if args.json else _human(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
