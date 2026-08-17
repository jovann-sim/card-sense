"""Agent-quality reporting from golden gates and production run evidence."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median


TERMINAL_STAGE_STATUSES = {"ok", "degraded", "failed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _suite_fingerprint() -> str:
    from evals.golden_cases import CASES_BY_AGENT

    payload = json.dumps(CASES_BY_AGENT, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def golden_report(store, uid: str, *, force: bool = False) -> dict:
    """Return the current golden result, rerunning only when its corpus changes."""
    fingerprint = _suite_fingerprint()
    saved = store.get_subdoc(uid, "quality_reports", "golden-latest")
    if saved and saved.get("suiteFingerprint") == fingerprint and not force:
        return {key: value for key, value in saved.items() if key != "id"}

    from evals.run_agent_evals import run_suite

    result = run_suite()
    report = {
        "suiteFingerprint": fingerprint,
        "evaluatedAt": _now(),
        "passed": result["passed"],
        "casesPassed": sum(metrics["casesPassed"] for metrics in result["agents"].values()),
        "casesTotal": sum(metrics["casesTotal"] for metrics in result["agents"].values()),
        "assertionsPassed": sum(metrics["assertionsPassed"] for metrics in result["agents"].values()),
        "assertionsTotal": sum(metrics["assertionsTotal"] for metrics in result["agents"].values()),
        "unsupportedClaims": result["qualityGates"]["unsupportedClaims"],
        "agents": result["agents"],
    }
    store.set_subdoc(uid, "quality_reports", "golden-latest", report)
    return report


def _live_metrics(agent_runs: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in agent_runs:
        if entry.get("runId"):
            grouped[str(entry["runId"])].append(entry)

    terminal_runs = []
    for run_id, entries in grouped.items():
        statuses = {entry.get("status") for entry in entries}
        agents = {entry.get("agent") for entry in entries}
        terminal = "failed" in statuses or (
            len(agents) >= 5 and statuses <= {"ok", "degraded"}
        )
        if terminal:
            terminal_runs.append((run_id, entries))

    degraded = sum(any(row.get("status") == "degraded" for row in rows)
                   for _run_id, rows in terminal_runs)
    failed = sum(any(row.get("status") == "failed" for row in rows)
                 for _run_id, rows in terminal_runs)
    run_durations = [
        sum(float(row.get("durationMs") or 0) for row in rows)
        for _run_id, rows in terminal_runs
    ]

    by_agent = []
    known_agents = ("ingestion", "card-intelligence", "strategy", "forecast", "advisory")
    for agent in known_agents:
        rows = [
            row for row in agent_runs
            if row.get("agent") == agent and row.get("status") in TERMINAL_STAGE_STATUSES
        ]
        durations = [float(row.get("durationMs") or 0) for row in rows]
        by_agent.append({
            "id": agent,
            "executions": len(rows),
            "degraded": sum(row.get("status") == "degraded" for row in rows),
            "failed": sum(row.get("status") == "failed" for row in rows),
            "medianDurationMs": round(median(durations), 2) if durations else None,
        })

    engines: dict[str, int] = defaultdict(int)
    for _run_id, rows in terminal_runs:
        engine = next((row.get("engine") for row in rows if row.get("engine")), "unknown")
        engines[str(engine)] += 1

    total = len(terminal_runs)
    return {
        "runsObserved": len(grouped),
        "terminalRuns": total,
        "degradedRuns": degraded,
        "failedRuns": failed,
        "degradedRate": round(degraded / total, 4) if total else None,
        "failedRate": round(failed / total, 4) if total else None,
        "medianRunDurationMs": round(median(run_durations), 2) if run_durations else None,
        "engines": dict(sorted(engines.items())),
        "agents": by_agent,
    }


def _outcome_metrics(advice: list[dict]) -> dict:
    measured = [
        row for row in advice
        if isinstance(row.get("predicted"), (int, float))
        and isinstance(row.get("actual"), (int, float))
    ]
    if not measured:
        return {
            "status": "not-measured",
            "evaluated": 0,
            "meanAbsoluteError": None,
            "note": "No recommendation has both predicted and actual reward value yet.",
        }
    errors = [abs(float(row["predicted"]) - float(row["actual"])) for row in measured]
    return {
        "status": "measured",
        "evaluated": len(measured),
        "meanAbsoluteError": round(sum(errors) / len(errors), 2),
        "note": "Error compares persisted predicted and actual nominal reward value.",
    }


def _model_metrics(calls: list[dict]) -> dict:
    """Aggregate recorded usage; estimates were fixed at call time."""
    input_tokens = sum(int(row.get("inputTokens") or 0) for row in calls)
    output_tokens = sum(int(row.get("outputTokens") or 0) for row in calls)
    thinking_tokens = sum(int(row.get("thinkingTokens") or 0) for row in calls)
    total_tokens = sum(int(row.get("totalTokens") or 0) for row in calls)
    estimated = round(sum(float(row.get("estimatedCostUsd") or 0) for row in calls), 6)
    successful = sum(row.get("status") == "ok" for row in calls)
    failures = len(calls) - successful

    by_agent = []
    for agent in ("card-intelligence", "advisory"):
        rows = [row for row in calls if row.get("agent") == agent]
        by_agent.append({
            "id": agent,
            "calls": len(rows),
            "inputTokens": sum(int(row.get("inputTokens") or 0) for row in rows),
            "outputTokens": sum(int(row.get("outputTokens") or 0) for row in rows),
            "thinkingTokens": sum(int(row.get("thinkingTokens") or 0) for row in rows),
            "estimatedUsd": round(sum(float(row.get("estimatedCostUsd") or 0) for row in rows), 6),
        })

    models: dict[str, int] = defaultdict(int)
    for row in calls:
        models[str(row.get("model") or "unknown")] += 1

    measured = total_tokens > 0
    return {
        "status": "measured" if measured else "not-measured",
        "calls": len(calls),
        "successfulCalls": successful,
        "failedCalls": failures,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "thinkingTokens": thinking_tokens,
        "totalTokens": total_tokens,
        "estimatedUsd": estimated if measured else None,
        "models": dict(sorted(models.items())),
        "agents": by_agent,
        "note": (
            "Estimate uses the Vertex AI per-token rates saved with each call."
            if measured else
            "No response with token usage has been recorded yet; unavailable and failed calls are still counted."
        ),
    }


def build_quality_report(store, uid: str, *, force_golden: bool = False) -> dict:
    """Combine invariant gates with evidence accumulated by real agent runs."""
    return {
        "generatedAt": _now(),
        "golden": golden_report(store, uid, force=force_golden),
        "live": _live_metrics(store.get_subcollection(uid, "agent_runs")),
        "outcomes": _outcome_metrics(store.get_subcollection(uid, "advice")),
        "modelCost": _model_metrics(store.get_subcollection(uid, "model_calls")),
    }
