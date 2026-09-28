"""
Streamlit chat UI. Pure I/O layer: reads the customer's text, invokes the
shared graph, displays the response. No business/routing logic lives here.

AUTH NOTE (demo vs. production):
  Demo:       sidebar picker selects one of a few seeded Customer rows —
              simulates "already logged in", but is NOT real authentication.
  Production: replace the picker with a real login/session step (OAuth,
              your app's own auth) and set customer_id from the
              authenticated session — never from free text the user types,
              and never from anything the LLM outputs.

Run with:
    streamlit run interfaces/chat_app.py
"""

import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from config import settings  # noqa: E402
from db.models import Customer  # noqa: E402
from db.session import get_session, init_db  # noqa: E402
from graph import build_graph  # noqa: E402
from interfaces.text_utils import extract_text  # noqa: E402

st.set_page_config(page_title="CircuitWorks Support", page_icon="🔌")
st.title("🔌 CircuitWorks Support")

settings.validate()
init_db()


def load_demo_customers() -> list[dict]:
    with get_session() as session:
        customers = session.query(Customer).order_by(Customer.id).all()
        return [{"id": c.id, "name": c.name} for c in customers]


demo_customers = load_demo_customers()

if "graph" not in st.session_state:
    st.session_state.graph = build_graph()
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "display_messages" not in st.session_state:
    st.session_state.display_messages = []

with st.sidebar:
    st.markdown("**Demo login**")
    st.caption(
        "⚠️ Demo only: picks a pre-seeded customer to simulate an "
        "authenticated identity. A real deployment would use actual login."
    )
    if not demo_customers:
        st.error("No demo customers found. Run `python -m scripts.seed_demo_data` first.")
        st.stop()

    selected_name = st.selectbox(
        "Acting as customer",
        options=[c["name"] for c in demo_customers],
    )
    customer_id = next(c["id"] for c in demo_customers if c["name"] == selected_name)
    st.caption(f"customer_id: `{customer_id}`")
    st.caption(f"Thread: `{st.session_state.thread_id}`")

# Changing the acting customer mid-session starts a fresh thread, so one
# person's conversation history/checkpoint never leaks into another's.
if st.session_state.get("active_customer_id") != customer_id:
    st.session_state.active_customer_id = customer_id
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.display_messages = []

for msg in st.session_state.display_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_input = st.chat_input("Ask about a product, place an order, or ask about policy...")

if user_input:
    st.session_state.display_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    graph_input = {
        "messages": [HumanMessage(content=user_input)],
        "customer_id": customer_id,
        "conversation_id": st.session_state.thread_id,
    }

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            result = st.session_state.graph.invoke(graph_input, config=config)

        if "__interrupt__" in result:
            interrupt_payload = result["__interrupt__"][0].value
            reply = interrupt_payload.get("message", "You're being connected to a human agent.")
        else:
            last_ai = next(
                (m for m in reversed(result["messages"]) if isinstance(m, AIMessage)),
                None,
            )
            reply = extract_text(last_ai.content) if last_ai else "(no response)"

        st.markdown(reply)

    st.session_state.display_messages.append({"role": "assistant", "content": reply})
