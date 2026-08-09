from __future__ import annotations

import json
import logging
from typing import Any

from ..config import settings

log = logging.getLogger(__name__)


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

    def __init__(self):
        self._client = None
        self._checked = False

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
        client = self._get_client()
        if not client:
            return fallback
        prompt = f"{system}\n\nReturn valid JSON only. INPUT:\n{json.dumps(payload, default=str)}"
        try:
            response = client.models.generate_content(
                model=settings.finance_agent_model, contents=prompt
            )
            text = (response.text or "").strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(text)
        except Exception as exc:
            log.warning("Gemini json call failed: %s", exc)
            return fallback

    def structured(self, prompt: str, schema, *, document=None, temperature: float = 0.0):
        """Schema-constrained call. Returns a validated instance of `schema`.

        Passing a response schema is what makes extraction dependable — the model
        returns the declared shape rather than prose we then have to salvage.
        Raises ModelUnavailable so callers can tell infrastructure failure apart
        from a document that genuinely has nothing in it.
        """
        client = self._get_client()
        if not client:
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
            if "quota" in lowered or "429" in lowered or "resource_exhausted" in lowered:
                raise ModelUnavailable("rate_limited", "Gemini quota was exhausted for this project.") from exc
            if "permission" in lowered or "403" in lowered:
                raise ModelUnavailable("model_unavailable", "This project is not permitted to call the model.") from exc
            raise ModelUnavailable("model_unavailable", f"Gemini call failed: {message[:200]}") from exc

        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return parsed

        raw = (response.text or "").strip().removeprefix("```json").removesuffix("```").strip()
        if not raw:
            raise ModelUnavailable("model_unavailable", "Gemini returned an empty response.")
        try:
            return schema.model_validate(json.loads(raw))
        except Exception as exc:
            raise ModelUnavailable("model_unavailable", "Gemini returned a response that did not match the schema.") from exc
