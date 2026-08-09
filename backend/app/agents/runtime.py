from __future__ import annotations
import json
from typing import Any
from ..config import settings

class GeminiRuntime:
    def __init__(self):
        self.client = None
        if not settings.demo_mode:
            from google import genai
            self.client = genai.Client(vertexai=True, project=settings.google_cloud_project, location=settings.google_cloud_location)

    def json(self, system: str, payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        if not self.client:
            return fallback
        prompt = f"{system}\n\nReturn valid JSON only. INPUT:\n{json.dumps(payload, default=str)}"
        try:
            response = self.client.models.generate_content(model=settings.finance_agent_model, contents=prompt)
            return json.loads((response.text or "").strip().removeprefix("```json").removesuffix("```").strip())
        except Exception:
            return fallback
