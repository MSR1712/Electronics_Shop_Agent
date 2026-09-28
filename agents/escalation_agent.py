"""
Escalation node: summarizes the conversation and hands off to a human via
escalate_to_human (log + Slack notify + interrupt()). Terminal node for
any thread the other three agents can't resolve.
"""

from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from llm import get_llm
from tools.escalation_tools import make_escalation_tool

SYSTEM_PROMPT = """You are the escalation handler for CircuitWorks. Your only
job is to summarize the customer's issue concisely and call
escalate_to_human with that summary as `reason`.

After calling the tool, relay its returned message to the customer warmly —
don't invent a different message. Do not attempt to resolve the underlying
issue yourself; that's precisely what escalation is for.
"""


def escalation_agent_node(state: dict) -> dict:
    customer_id = state.get("customer_id")
    if not customer_id:
        raise ValueError("escalation_agent_node requires an authenticated customer_id in state")

    # conversation_id is now available directly on state — thread it
    # through so escalation rows are traceable back to the actual thread.
    tools = make_escalation_tool(customer_id, conversation_id=state.get("conversation_id"))
    agent = create_react_agent(
        model=get_llm(),
        tools=tools,
        prompt=SystemMessage(content=SYSTEM_PROMPT),
    )
    result = agent.invoke({"messages": state["messages"]})
    new_messages = result["messages"][len(state["messages"]):]
    return {"messages": new_messages, "escalated": True}
