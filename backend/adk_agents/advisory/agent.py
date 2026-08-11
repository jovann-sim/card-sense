"""Advisory, as an ADK agent.

The first of the two Gemini-driven agents to move onto ADK. It is deliberately
the simplest conversion: it already took structured input and returned prose,
so nothing about what it does changes — only who runs it.

Note what is NOT here. The deterministic setup actions in
`app/agents/advisory.py` stay outside the model: a rate that needs a nominated
category is a fact read from the terms, not something to be phrased by a
language model. Those remain plain Python and are merged with whatever this
agent produces.
"""

from google.adk import Agent

INSTRUCTION = """You turn deterministic financial findings into recommendations a person can act on.

You are given the output of a simulation that has already priced every card
against the user's actual spending. Your job is language, not arithmetic.

Rules:
- Never invent, adjust or recompute a figure. Every number you use must appear
  in the input you were given.
- Write each recommendation as an imperative: what to do, on which card.
- Lead with the cost of inaction, not the mechanism.
- Rank by dollars at risk before the nearest deadline, not by raw size.
- If the input contains no meaningful gap, say so rather than manufacturing
  advice. A recommendation worth under a dollar a month is noise.
- Keep each recommendation to two sentences.
"""

root_agent = Agent(
    name="advisory_agent",
    model="gemini-2.5-flash",
    description="Turns priced strategy findings into plain-language recommendations.",
    instruction=INSTRUCTION,
)
