from __future__ import annotations
from datetime import datetime, timedelta
from .runtime import GeminiRuntime

class CardIntelligenceAgent:
    id="card-intelligence"
    def __init__(self, runtime): self.runtime=runtime
    def parse(self, card):
        fallback={"rules":[],"status":"failed","note":"Terms could not be parsed confidently; card excluded from comparisons."}
        if not card.get("termsText"):
            return fallback
        result=self.runtime.json("Extract reward rules. Return rules with categoryLabel, rate, cap, cycleLabel; status parsed or failed. Do not guess.",{"terms":card["termsText"]},fallback)
        if not result.get("rules"):
            return fallback
        return result | {"status":"parsed"}
