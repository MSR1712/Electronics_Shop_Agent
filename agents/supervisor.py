"""
Supervisor/router node. Classifies the latest customer message into one of
four intents and writes it to state["intent"]. The actual routing (which
node runs next) happens via a conditional edge in graph.py that reads this
field — the supervisor itself doesn't call sub-agents directly.

Uses temperature=0 and structured output for a clean, deterministic label
rather than free-text the graph would need to parse.
"""

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from agents.state import GraphState, Intent
from llm import get_llm

CLASSIFY_PROMPT = """You are a routing classifier for a customer support
system at CircuitWorks, an electronics/robotics component shop. Classify
the customer's most recent message into exactly one category:

- product_info: questions about component specs, pinouts, voltage, package
  type, pricing, stock, what a part does, comparisons between parts.
- order: placing a new order, or asking about the status of an existing order.
- policy_support: questions about returns, warranty, shipping policy, FAQs,
  or general account questions not tied to a specific order.
- escalation: an explicit request to speak with a human, or a complaint/
  expression of frustration about something that ALREADY happened (a bad
  order, an unresolved prior issue, dissatisfaction with a previous answer
  in this conversation). Do not use escalation just because a message is a
  greeting, small talk, or doesn't obviously fit another category — that's
  "unclear", not escalation. Only escalate when the customer has clearly
  signaled they want a human or are upset about something concrete.

If the message is a greeting, small talk, or is genuinely ambiguous even
considering conversation history, classify it as "unclear".

Conversation so far:
{history}

Classify only the most recent customer message."""


class RouteDecision(BaseModel):
    intent: Intent = Field(description="One of: product_info, order, policy_support, escalation, unclear")
    reasoning: str = Field(description="One-sentence justification, for logging/debugging")


def _format_history(messages: list) -> str:
    lines = []
    for m in messages[-8:]:  # last few turns is enough context for routing
        role = "Customer" if isinstance(m, HumanMessage) else "Assistant"
        lines.append(f"{role}: {m.content}")
    return "\n".join(lines)


def supervisor_node(state: GraphState) -> dict:
    llm = get_llm(temperature=0)
    structured_llm = llm.with_structured_output(RouteDecision)

    history = _format_history(state["messages"])
    decision = structured_llm.invoke(CLASSIFY_PROMPT.format(history=history))

    return {"intent": decision.intent}


def route_from_supervisor(state: GraphState) -> str:
    """
    Conditional edge function: maps state["intent"] to the node name to run
    next. "unclear" routes to policy_support as a safe general-help default
    rather than escalation, so we don't hand off to a human for every vague
    first message — the sub-agent can ask a clarifying question, and if it
    still can't help, it can itself route to escalation on the next turn.
    """
    intent = state.get("intent", "unclear")
    mapping = {
        "product_info": "product_agent",
        "order": "order_agent",
        "policy_support": "policy_agent",
        "escalation": "escalation_agent",
        "unclear": "policy_agent",
    }
    return mapping.get(intent, "policy_agent")
