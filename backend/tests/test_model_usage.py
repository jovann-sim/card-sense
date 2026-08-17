from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from adk_agents.pipeline.runner import run_pipeline
from app.agents.runtime import GeminiRuntime, ModelUnavailable
from app.agents.schema import ExtractionResult
from app.agents.terms import document_from_text
from app.orchestrator import Orchestrator
from app.quality import build_quality_report
from app.store import Store


UID = "usage-user"


class Output(BaseModel):
    answer: str


class Models:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def generate_content(self, **_kwargs):
        if self.error:
            raise self.error
        return self.response


def response(*, parsed=None, text=""):
    return SimpleNamespace(
        parsed=parsed,
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=1_000,
            candidates_token_count=200,
            thoughts_token_count=50,
            cached_content_token_count=0,
            total_token_count=1_250,
        ),
    )


def runtime_with(store, response=None, error=None):
    runtime = GeminiRuntime(store)
    runtime._checked = True
    runtime._client = SimpleNamespace(models=Models(response, error))
    return runtime


def test_structured_call_persists_tokens_cost_and_run_context_without_content():
    store = Store()
    runtime = runtime_with(store, response(parsed=Output(answer="safe result")))

    with runtime.context(UID, "run-123", "card-intelligence"):
        result = runtime.structured(
            "SECRET PROMPT", Output,
            document=SimpleNamespace(is_pdf=False, text="PRIVATE CARD TERMS"),
        )

    assert result.answer == "safe result"
    calls = store.get_subcollection(UID, "model_calls")
    assert len(calls) == 1
    call = calls[0]
    assert call["runId"] == "run-123"
    assert call["agent"] == "card-intelligence"
    assert call["status"] == "ok"
    assert call["inputTokens"] == 1_000
    assert call["outputTokens"] == 200
    assert call["thinkingTokens"] == 50
    assert call["totalTokens"] == 1_250
    assert call["estimatedCostUsd"] == pytest.approx(0.000445)
    serialized = str(call)
    assert "SECRET PROMPT" not in serialized
    assert "PRIVATE CARD TERMS" not in serialized
    assert "safe result" not in serialized
    assert not ({"prompt", "payload", "document", "response"} & set(call))


def test_json_call_records_usage_but_not_its_payload():
    store = Store()
    runtime = runtime_with(store, response(text='{"answer": "ok"}'))

    with runtime.context(UID, "run-json", "advisory"):
        result = runtime.json("SECRET SYSTEM", {"private": "DO NOT STORE"}, {})

    assert result == {"answer": "ok"}
    call = store.get_subcollection(UID, "model_calls")[0]
    assert call["operation"] == "json"
    assert call["agent"] == "advisory"
    assert "DO NOT STORE" not in str(call)


def test_unavailable_model_is_counted_without_inventing_tokens_or_cost():
    store = Store()
    runtime = GeminiRuntime(store)
    runtime._checked = True
    runtime._client = None

    with runtime.context(UID, None, "card-intelligence", source="card-add"):
        with pytest.raises(ModelUnavailable):
            runtime.structured("prompt", Output)

    call = store.get_subcollection(UID, "model_calls")[0]
    assert call["status"] == "unavailable"
    assert call["source"] == "card-add"
    assert call["runId"] is None
    assert call["totalTokens"] == 0
    assert call["estimatedCostUsd"] == 0

    quality = build_quality_report(store, UID)["modelCost"]
    assert quality["status"] == "not-measured"
    assert quality["calls"] == 1
    assert quality["successfulCalls"] == 0
    assert quality["failedCalls"] == 1
    assert quality["estimatedUsd"] is None


def test_quality_report_aggregates_usage_by_agent_and_model():
    store = Store()
    for ident, agent, cost in (
        ("one", "card-intelligence", 0.001),
        ("two", "advisory", 0.002),
    ):
        store.set_subdoc(UID, "model_calls", ident, {
            "model": "gemini-2.5-flash", "agent": agent, "status": "ok",
            "inputTokens": 100, "outputTokens": 20, "thinkingTokens": 5,
            "totalTokens": 125, "estimatedCostUsd": cost,
        })

    quality = build_quality_report(store, UID)["modelCost"]

    assert quality["status"] == "measured"
    assert quality["calls"] == quality["successfulCalls"] == 2
    assert quality["failedCalls"] == 0
    assert quality["inputTokens"] == 200
    assert quality["outputTokens"] == 40
    assert quality["thinkingTokens"] == 10
    assert quality["totalTokens"] == 250
    assert quality["estimatedUsd"] == 0.003
    assert quality["models"] == {"gemini-2.5-flash": 2}
    assert {row["id"]: row["calls"] for row in quality["agents"]} == {
        "card-intelligence": 1,
        "advisory": 1,
    }


def test_adk_model_calls_are_correlated_to_the_pipeline_run(monkeypatch):
    store = Store()
    store.set_subdoc(UID, "wallet", "due-card", {
        "cardId": "due-card", "name": "Due Card", "last4": "1234",
        "network": "Visa", "track": "cashback", "parseStatus": "parsed",
        "termsUrl": "https://issuer.test/terms", "nextRecheckAt": "2020-01-01",
    })
    extraction = ExtractionResult.model_validate({
        "confidence": 0.95,
        "rules": [{
            "categoryLabel": "Everything else", "tier": "base",
            "rewards": [{
                "rewardType": "cashback", "rateValue": 1, "rateUnit": "percent",
            }],
        }],
    })
    orchestrator = Orchestrator(store)
    orchestrator.runtime._checked = True
    orchestrator.runtime._client = SimpleNamespace(
        models=Models(response(parsed=extraction)),
    )
    monkeypatch.setattr(
        orchestrator.cardintel,
        "_resolve_document",
        lambda _card: (document_from_text("Earn one percent."), None),
    )

    run_pipeline(
        UID, "usage correlation", run_id="adk-usage-run",
        active_orchestrator=orchestrator,
    )

    calls = store.get_subcollection(UID, "model_calls")
    assert len(calls) == 2  # Card Intelligence intentionally reads twice.
    assert {call["runId"] for call in calls} == {"adk-usage-run"}
    assert {call["agent"] for call in calls} == {"card-intelligence"}
    assert {call["source"] for call in calls} == {"pipeline"}
