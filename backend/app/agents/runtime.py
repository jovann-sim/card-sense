from __future__ import annotations

import json
import logging
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from ..config import settings

log = logging.getLogger(__name__)

_CALL_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "cardsense_model_call_context", default=None,
)


class ModelUnavailable(Exception):
    """Gemini could not be reached or refused the request.

    Deliberately distinct from "the model read the document and found nothing":
    one is our problem, the other is the document's, and the interface renders
    them differently.
    """

    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


class GeminiRuntime:
    """Thin wrapper over the Gen AI SDK.

    The client is built lazily so importing the app never requires credentials,
    and so a missing project degrades one agent instead of failing startup.
    """

    def __init__(self, store=None):
        self._client = None
        self._checked = False
        self.store = store

    @contextmanager
    def context(
        self,
        uid: str,
        run_id: str | None,
        agent: str,
        *,
        source: str = "pipeline",
    ):
        """Attach privacy-safe ownership metadata to calls in this execution."""
        token = _CALL_CONTEXT.set({
            "uid": uid, "runId": run_id, "agent": agent, "source": source,
        })
        try:
            yield
        finally:
            _CALL_CONTEXT.reset(token)

    @property
    def available(self) -> bool:
        return self._get_client() is not None

    def _get_client(self):
        if self._checked:
            return self._client
        self._checked = True
        if not settings.use_gemini:
            log.info("Gemini disabled: no GOOGLE_CLOUD_PROJECT configured.")
            return None
        try:
            from google import genai

            self._client = genai.Client(
                vertexai=True,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
            )
        except Exception as exc:
            log.warning("Gemini unavailable: %s", exc)
            self._client = None
        return self._client

    def json(self, system: str, payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        """Loose JSON call used by the advisory agent. Never raises."""
        started = perf_counter()
        client = self._get_client()
        if not client:
            self._record("json", "unavailable", started)
            return fallback
        prompt = f"{system}\n\nReturn valid JSON only. INPUT:\n{json.dumps(payload, default=str)}"
        response = None
        try:
            response = client.models.generate_content(
                model=settings.finance_agent_model, contents=prompt
            )
            text = (response.text or "").strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(text)
            self._record("json", "ok", started, response=response)
            return parsed
        except Exception as exc:
            log.warning("Gemini json call failed: %s", exc)
            self._record(
                "json", "invalid-response" if response is not None else self._failure_status(exc),
                started, response=response,
            )
            return fallback

    def structured(self, prompt: str, schema, *, document=None, temperature: float = 0.0):
        """Schema-constrained call. Returns a validated instance of `schema`.

        Passing a response schema is what makes extraction dependable — the model
        returns the declared shape rather than prose we then have to salvage.
        Raises ModelUnavailable so callers can tell infrastructure failure apart
        from a document that genuinely has nothing in it.
        """
        started = perf_counter()
        client = self._get_client()
        if not client:
            self._record("structured", "unavailable", started)
            raise ModelUnavailable(
                "model_unavailable",
                "Gemini is not configured; set GOOGLE_CLOUD_PROJECT to enable document reading.",
            )

        from google.genai import types

        parts: list[Any] = []
        if document is not None and document.is_pdf:
            parts.append(types.Part.from_bytes(data=document.data, mime_type=document.mime_type))
        elif document is not None and document.text:
            parts.append(types.Part.from_text(text=f"DOCUMENT:\n{document.text}"))
        parts.append(types.Part.from_text(text=prompt))

        response = None
        try:
            response = client.models.generate_content(
                model=settings.finance_agent_model,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
        except Exception as exc:
            message = str(exc)
            lowered = message.lower()
            self._record("structured", self._failure_status(exc), started)
            if "quota" in lowered or "429" in lowered or "resource_exhausted" in lowered:
                raise ModelUnavailable("rate_limited", "Gemini quota was exhausted for this project.") from exc
            if "permission" in lowered or "403" in lowered:
                raise ModelUnavailable("model_unavailable", "This project is not permitted to call the model.") from exc
            raise ModelUnavailable("model_unavailable", f"Gemini call failed: {message[:200]}") from exc

        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            self._record("structured", "ok", started, response=response)
            return parsed

        raw = (response.text or "").strip().removeprefix("```json").removesuffix("```").strip()
        if not raw:
            self._record("structured", "invalid-response", started, response=response)
            raise ModelUnavailable("model_unavailable", "Gemini returned an empty response.")
        try:
            parsed = schema.model_validate(json.loads(raw))
            self._record("structured", "ok", started, response=response)
            return parsed
        except Exception as exc:
            self._record("structured", "invalid-response", started, response=response)
            raise ModelUnavailable("model_unavailable", "Gemini returned a response that did not match the schema.") from exc

    @staticmethod
    def _failure_status(exc: Exception) -> str:
        lowered = str(exc).lower()
        if "quota" in lowered or "429" in lowered or "resource_exhausted" in lowered:
            return "rate-limited"
        if "permission" in lowered or "403" in lowered:
            return "permission-denied"
        return "failed"

    @staticmethod
    def _usage(response) -> dict[str, int]:
        usage = getattr(response, "usage_metadata", None) if response is not None else None
        prompt = int(getattr(usage, "prompt_token_count", 0) or 0)
        output = int(getattr(usage, "candidates_token_count", 0) or 0)
        thinking = int(getattr(usage, "thoughts_token_count", 0) or 0)
        cached = int(getattr(usage, "cached_content_token_count", 0) or 0)
        total = int(getattr(usage, "total_token_count", 0) or 0)
        return {
            "inputTokens": prompt,
            "outputTokens": output,
            "thinkingTokens": thinking,
            "cachedInputTokens": cached,
            "totalTokens": total or prompt + output + thinking,
        }

    def _record(self, operation: str, status: str, started: float, *, response=None) -> None:
        """Persist usage only; prompts, documents and model output never enter telemetry."""
        context = _CALL_CONTEXT.get()
        if not self.store or not context or not context.get("uid"):
            return
        usage = self._usage(response)
        input_rate = settings.gemini_input_usd_per_million
        output_rate = settings.gemini_output_usd_per_million
        thinking_rate = settings.gemini_thinking_usd_per_million
        estimated = (
            usage["inputTokens"] * input_rate
            + usage["outputTokens"] * output_rate
            + usage["thinkingTokens"] * thinking_rate
        ) / 1_000_000
        call_id = uuid.uuid4().hex
        record = {
            "model": settings.finance_agent_model,
            "operation": operation,
            "status": status,
            "agent": context["agent"],
            "runId": context.get("runId"),
            "source": context.get("source", "pipeline"),
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "durationMs": round((perf_counter() - started) * 1000, 2),
            **usage,
            "estimatedCostUsd": round(estimated, 8),
            "pricing": {
                "currency": "USD",
                "unit": "per 1M tokens",
                "input": input_rate,
                "output": output_rate,
                "thinking": thinking_rate,
            },
        }
        try:
            self.store.set_subdoc(context["uid"], "model_calls", call_id, record)
        except Exception as exc:  # Telemetry must never take down financial advice.
            log.warning("Could not persist Gemini usage telemetry: %s", exc)
