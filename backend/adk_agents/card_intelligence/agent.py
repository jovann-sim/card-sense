"""Card intelligence, as an ADK agent.

The division of labour is the point of this file. The agent reads a document
and returns the reward structure it found, constrained by a schema. Everything
around that stays deterministic Python:

  fetching the document        a tool, because a URL fetch is not reasoning
  two-pass consolidation       arithmetic over two readings
  confidence gating            a threshold comparison
  MCC backfill                 a lookup table
  pricing to dollars           multiplication by a published valuation
  the failure taxonomy         a mapping of causes to states

Putting any of that behind a model would make figures the dashboard presents as
money non-reproducible, which is the second principle in the architecture.
"""

from google.adk import Agent

from app.agents.schema import EXTRACTION_PROMPT, ExtractionResult
from app.agents.terms import FetchError, fetch_terms


def read_terms_document(url: str) -> dict:
    """Fetch a credit card's published terms so they can be read.

    Args:
        url: Link to the issuer's terms — an HTML page or a PDF.

    Returns:
        The document's text and where it came from, or the reason it could not
        be retrieved. A failure here is the source's, not the document's, and
        the two are reported differently.
    """
    try:
        document = fetch_terms(url)
    except FetchError as exc:
        return {"ok": False, "reason": exc.reason, "detail": exc.detail}

    return {
        "ok": True,
        "kind": document.kind,
        "locator": document.locator,
        # A PDF is handed to the model as bytes elsewhere; this path carries
        # text so the tool result stays serialisable.
        "text": (document.text or "")[:100_000] if document.kind == "text" else None,
        "note": "This is a PDF; it is passed to the model directly rather than as text."
        if document.kind == "pdf" else None,
    }


root_agent = Agent(
    name="card_intelligence_agent",
    model="gemini-2.5-flash",
    description="Reads a credit card's published terms and returns its reward structure.",
    instruction=EXTRACTION_PROMPT + """

You may be given a URL rather than a document. Call read_terms_document to
retrieve it before extracting anything. If the tool reports a failure, return
an empty rules list rather than describing the card from memory: a rate you
recall is not a rate the document states, and a confident wrong number is worse
than an admitted gap.
""",
    tools=[read_terms_document],
    output_schema=ExtractionResult,
    output_key="extraction",
)
