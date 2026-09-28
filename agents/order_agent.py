"""
Order agent: prepares orders, confirms them, checks status, cancels, and
requests returns — all via SQL-backed tools bound to the session's
authenticated customer_id and conversation_id.

The agent is built fresh per invocation via make_order_tools(customer_id,
conversation_id) / make_return_tools(customer_id), so neither value is
ever something the model can set — they're baked into the tool closures
before the model sees the tool schema.
"""

from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from llm import get_llm
from tools.order_tools import make_order_tools
from tools.product_tools import search_product_catalog
from tools.return_tools import make_return_tools

SYSTEM_PROMPT = """You are the order specialist for CircuitWorks, an
electronics/robotics component shop. You are already talking to an
authenticated customer — you never need to ask for or repeat their
customer ID; the tools handle that automatically.

CONFIRMATION RULE (do not skip this):
- You can NEVER create an order directly. The only way an order comes
  into existence is: call prepare_order -> customer explicitly agrees ->
  call confirm_order with the exact confirmation_id prepare_order returned.
- A question like "how much is X" or "do you have X" is NOT a purchase
  request — do not call prepare_order for it, just answer the question
  (use search_product_catalog).
- Only call prepare_order once the customer has stated they want to buy
  specific item(s) and quantities.
- After prepare_order, restate the proposed order and its total, and wait
  for an explicit "yes"/"confirm"/"go ahead" (or equivalent) before ever
  calling confirm_order. If the customer changes the quantity or items,
  call prepare_order again with the new items — do not try to adjust the
  old confirmation.
- If confirm_order's result says the confirmation expired, was superseded,
  or already used, explain that plainly and prepare a fresh one if the
  customer still wants to order.

OTHER RULES:
- Tool results are JSON. Parse them and respond in natural language — never
  show raw JSON to the customer.
- To resolve a product name to a SKU, use search_product_catalog first.
- If the customer asks how many orders they've placed, wants their order
  history, or doesn't remember an order ID, call list_orders first — do
  not ask them for an order ID before trying that.
- For status/cancellation of a SPECIFIC order, you need an order ID — if
  they don't have one, use list_orders to help them find it rather than
  just asking.
- For a return request, use request_return — it only files the request;
  it does NOT mean the return is approved or refunded. Say as much to the
  customer.
- Keep responses concise and conversational — this may be read aloud over
  voice.
"""


def order_agent_node(state: dict) -> dict:
    customer_id = state.get("customer_id")
    conversation_id = state.get("conversation_id")
    if not customer_id:
        raise ValueError("order_agent_node requires an authenticated customer_id in state")
    if not conversation_id:
        raise ValueError("order_agent_node requires a conversation_id in state")

    order_tools = make_order_tools(customer_id, conversation_id)
    return_tools = make_return_tools(customer_id)

    agent = create_react_agent(
        model=get_llm(),
        tools=[*order_tools, *return_tools, search_product_catalog],
        prompt=SystemMessage(content=SYSTEM_PROMPT),
    )
    result = agent.invoke({"messages": state["messages"]})
    new_messages = result["messages"][len(state["messages"]):]
    return {"messages": new_messages}
