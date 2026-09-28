"""
Policy & support agent: returns/warranty/shipping policy + account-adjacent
questions. Policy content is DEMO DATA (LLM-generated) — see
tools/policy_tools.py docstring before using this in production.
"""

from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from llm import get_llm
from tools.order_tools import make_order_tools
from tools.policy_tools import search_policy

SYSTEM_PROMPT = """You are the policy & support specialist for CircuitWorks,
an electronics/robotics component shop. You answer questions about returns,
warranty, shipping policy, and general FAQs. You can also look up a specific
order's status if the customer's question is tied to an order.

Rules:
- ALWAYS call search_policy for any policy/FAQ question — never answer
  from general knowledge, since CircuitWorks' specific terms may differ
  from typical industry norms. If search_policy returns found=false, say
  you don't have that information rather than guessing.
- Use get_order_status only when the question is specifically about an
  order the customer has already placed and provided an ID for. You never
  need to ask for their customer ID — only the order ID.
- Tool results are JSON — parse them and respond in natural language, never
  show raw JSON.
- If a question is really an order-status or new-order request unrelated to
  policy, say so plainly rather than guessing an answer.
- If the customer's issue isn't resolvable with policy info or order status
  (e.g. a complaint, a request for an exception to stated policy, visible
  frustration), don't argue policy repeatedly — suggest escalating to a
  human.
- Keep answers concise and conversational; this may be read aloud over voice.
"""


def policy_agent_node(state: dict) -> dict:
    customer_id = state.get("customer_id")
    conversation_id = state.get("conversation_id")
    if not customer_id:
        raise ValueError("policy_agent_node requires an authenticated customer_id in state")
    if not conversation_id:
        raise ValueError("policy_agent_node requires a conversation_id in state")

    # Only get_order_status is relevant here, but make_order_tools returns
    # all four bound tools — that's fine, this agent's system prompt scopes
    # what it's actually supposed to use them for.
    order_tools = make_order_tools(customer_id, conversation_id)
    get_order_status_tool = [t for t in order_tools if t.name == "get_order_status"][0]

    agent = create_react_agent(
        model=get_llm(),
        tools=[search_policy, get_order_status_tool],
        prompt=SystemMessage(content=SYSTEM_PROMPT),
    )
    result = agent.invoke({"messages": state["messages"]})
    new_messages = result["messages"][len(state["messages"]):]
    return {"messages": new_messages}
