from __future__ import annotations

import json

from evals.golden_cases import CASES_BY_AGENT
from evals.run_agent_evals import evaluate_case, run_suite


def test_golden_corpus_is_machine_readable_and_covers_every_agent():
    assert set(CASES_BY_AGENT) == {
        "ingestion", "card-intelligence", "strategy", "forecast", "advisory",
    }
    assert all(len(cases) >= 3 for cases in CASES_BY_AGENT.values())
    assert all({case["risk"] for case in cases} & {"safety", "recovery"}
               for cases in CASES_BY_AGENT.values())
    json.dumps(CASES_BY_AGENT)


def test_all_golden_agent_quality_gates_pass():
    report = run_suite()

    assert report["passed"], [
        case for case in report["cases"] if not case["passed"]
    ]
    assert report["qualityGates"] == {
        "casePassRate": 1.0,
        "assertionPassRate": 1.0,
        "unsupportedClaims": 0,
    }


def test_a_changed_financial_expectation_fails_the_quality_gate():
    case = {
        **CASES_BY_AGENT["strategy"][0],
        "expect": {"captured": 999.0},
    }

    result = evaluate_case("strategy", case)

    assert result.passed is False
    assert "expected 999.0" in result.failures[0]

