"""Run card intelligence over the hard-card corpus and report what it managed.

This is a manual harness, not a unit test: it calls Gemini, costs money and
takes about a minute. Run it after changing the schema or the prompt.

    cd backend && source .venv/bin/activate && python -m evals.run_extraction_eval
"""

from __future__ import annotations

import sys
from collections import Counter

from app.agents.card_intelligence import CardIntelligenceAgent
from app.agents.runtime import GeminiRuntime
from evals.corpus import CORPUS


def condition_kinds(result: dict) -> set[str]:
    """Conditions live on rules and on benefits; a rebate qualifies either way."""
    sources = [*result.get("rules", []), *result.get("benefits", [])]
    return {
        condition.get("kind")
        for item in sources
        for condition in item.get("conditions") or []
        if isinstance(condition, dict)
    }


def check(entry: dict, result: dict) -> list[str]:
    """Compare what the entry says must be captured against what came back."""
    misses: list[str] = []
    expect = entry["expect"]
    rules = result.get("rules", [])

    if result["status"] != "parsed":
        return [f"status={result['status']} ({result.get('failureReason')})"]

    if expect.get("requiresSelection") and not any(r.get("requiresSelection") for r in rules):
        misses.append("nomination requirement not captured")

    captured = condition_kinds(result)
    # requiresSelection and a category_selection condition state the same fact.
    # Either is a capture; demanding both tests our encoding, not the reading.
    if any(r.get("requiresSelection") for r in rules):
        captured.add("category_selection")
    for kind in expect.get("conditions", set()):
        if kind not in captured:
            misses.append(f"condition '{kind}' not captured")

    if expect.get("reward_choice") and not any(r.get("hasRewardChoice") for r in rules):
        misses.append("reward-currency choice not captured")

    if expect.get("merchants") and not any(r.get("merchants") for r in rules):
        misses.append("merchant scoping not captured")

    if expect.get("mcc") and not any(r.get("mccCodes") for r in rules):
        misses.append("MCC codes not captured")

    if expect.get("exclusions") and not any(r.get("exclusions") for r in rules):
        misses.append("exclusions not captured")

    if expect.get("statement_credits") and not result.get("benefits"):
        misses.append("statement credits not captured")

    if expect.get("multiplier") and not result.get("characteristics", {}).get("multiplierTiers"):
        misses.append("relationship multiplier not captured")

    if expect.get("shared_cap") and not any(r.get("capGroup") for r in rules):
        misses.append("shared cap not captured")

    return misses


def main() -> int:
    agent = CardIntelligenceAgent(GeminiRuntime())
    if not agent.runtime.available:
        print("Gemini is not configured; set GOOGLE_CLOUD_PROJECT first.")
        return 2

    totals = Counter()
    unresolved_all: list[tuple[str, str]] = []

    for entry in CORPUS:
        result = agent.parse({
            "name": entry["name"], "track": entry["track"], "termsText": entry["terms"],
        })
        misses = check(entry, result)
        rules = result.get("rules", [])
        mcc_coverage = sum(1 for r in rules if r.get("mccCodes")) / len(rules) if rules else 0

        totals["cards"] += 1
        totals["parsed"] += result["status"] == "parsed"
        totals["clean"] += not misses
        totals["rules"] += len(rules)

        flag = "ok  " if not misses else "MISS"
        print(f"\n{flag} {entry['name']}")
        print(f"     {entry['stresses']}")
        print(f"     status={result['status']} confidence={result.get('confidence')} "
              f"rules={len(rules)} mcc_coverage={mcc_coverage:.0%}")
        for miss in misses:
            print(f"     ✗ {miss}")
        for note in result.get("unresolved") or []:
            unresolved_all.append((entry["name"], note))
            print(f"     ~ unresolved: {note[:110]}")

    print("\n" + "=" * 72)
    print(f"parsed {totals['parsed']}/{totals['cards']}   "
          f"fully captured {totals['clean']}/{totals['cards']}   "
          f"rules extracted {totals['rules']}")
    print(f"structures reported as unresolved: {len(unresolved_all)}")
    return 0 if totals["clean"] == totals["cards"] else 1


if __name__ == "__main__":
    sys.exit(main())
