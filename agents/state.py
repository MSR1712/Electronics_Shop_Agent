"""
Shared graph state. Every node (supervisor + all sub-agents) reads/writes
this same TypedDict, which is what makes voice and chat genuinely share
one brain: whichever I/O layer is in front, it only ever appends a
HumanMessage to `messages` and reads the final AIMessage back out.
"""

from typing import Annotated, Any, Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

Intent = Literal["product_info", "order", "policy_support", "escalation", "unclear"]


class GraphState(TypedDict):
    # Full conversation history. `add_messages` reducer means nodes only
    # return the *new* message(s) they produced; LangGraph appends them.
    messages: Annotated[list[BaseMessage], add_messages]

    # Identifies the customer for order lookups, account-specific policy
    # questions, and escalation logging. Set by the I/O layer at session start.
    customer_id: Optional[str]

    # Identifies this conversation thread (the I/O layer's session/thread
    # id — same value used as LangGraph's checkpoint thread_id). Required
    # by the order confirmation workflow: a pending confirmation is scoped
    # to (customer_id, conversation_id) so it can't be confirmed from a
    # different conversation. See tools/order_tools.py.
    conversation_id: Optional[str]

    # Set by the supervisor node after classification; read by the
    # conditional edge to decide which sub-agent to route to.
    intent: Optional[Intent]

    # RAG context retrieved by search_product_catalog / search_policy,
    # kept here so a sub-agent's final response-generation step can see
    # what was retrieved without re-querying.
    retrieved_context: Optional[list[str]]

    # Results of any tool calls in this turn (order confirmations, status
    # lookups, etc.) — kept separate from `messages` so nodes can inspect
    # structured results without re-parsing message text.
    tool_results: Optional[dict[str, Any]]

    # Set when the escalation node determines a human handoff is needed.
    # Downstream I/O layers can check this to show a "connecting you to
    # a human" message.
    escalated: Optional[bool]
