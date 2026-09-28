"""
Assembles the single shared LangGraph "brain". Both the chat and voice
interfaces import `build_graph()` from here and invoke the same compiled
graph — no business logic is duplicated between channels.

Flow:
    START -> supervisor -> (conditional) -> {product_agent | order_agent |
             policy_agent | escalation_agent} -> END

Checkpointing is SQLite-backed (not in-memory), so conversation state
survives an app restart and works across the Streamlit and voice
processes independently — required for interrupt()-based escalation to
resume correctly, and for conversations to persist at all in production.
For a multi-worker deployment, point this at Postgres instead
(langgraph.checkpoint.postgres.PostgresSaver) using the same DATABASE_URL
pattern as db/session.py.
"""

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from agents.escalation_agent import escalation_agent_node
from agents.order_agent import order_agent_node
from agents.policy_agent import policy_agent_node
from agents.product_agent import product_agent_node
from agents.state import GraphState
from agents.supervisor import route_from_supervisor, supervisor_node

CHECKPOINT_DB_PATH = "./langgraph_checkpoints.sqlite"


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("product_agent", product_agent_node)
    graph.add_node("order_agent", order_agent_node)
    graph.add_node("policy_agent", policy_agent_node)
    graph.add_node("escalation_agent", escalation_agent_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "product_agent": "product_agent",
            "order_agent": "order_agent",
            "policy_agent": "policy_agent",
            "escalation_agent": "escalation_agent",
        },
    )
    graph.add_edge("product_agent", END)
    graph.add_edge("order_agent", END)
    graph.add_edge("policy_agent", END)
    graph.add_edge("escalation_agent", END)

    # Constructed from a raw sqlite3 connection (rather than
    # SqliteSaver.from_conn_string, which is a context manager in some
    # versions) so the connection stays open for the graph's whole
    # lifetime without the caller needing a `with` block. check_same_thread
    # is disabled for the same reason as db/session.py — Streamlit/FastAPI
    # use worker threads.
    conn = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return graph.compile(checkpointer=checkpointer)
