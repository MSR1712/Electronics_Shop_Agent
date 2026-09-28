"""Product info agent: answers spec/pricing/stock questions via RAG + web fallback."""

from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from llm import get_llm
from tools.product_tools import search_product_catalog, web_search_specs

SYSTEM_PROMPT = """You are the product-info specialist for CircuitWorks, an
electronics/robotics component shop. You answer customer questions about
component specs, pinouts, voltage, package types, pricing, and stock levels.

Rules:
- ALWAYS call search_product_catalog first for any product question.
- Only call web_search_specs if the catalog search returns no relevant match
  AND the customer is asking about a specific named part — never guess specs
  from memory.
- If a product is out of stock, say so plainly and don't imply it can be
  ordered.
- Be precise with numbers (voltage, current, dimensions) — don't round or
  approximate specs you retrieved.
- Keep answers concise; this may be read aloud over voice, so avoid dense
  tables or long bullet lists when a sentence or two will do.
- If the customer asks to see a picture/photo/image of a product, use the
  image_url from search_product_catalog's result and embed it in your reply
  as Markdown: ![name](image_url). If image_url is missing/None, say no
  image is available for that item instead of inventing a URL. These are
  placeholder demo images, not real product photography — if asked, say so
  plainly rather than claiming otherwise.
"""

def product_agent_node(state: dict) -> dict:
    # Built per-call, consistent with the other three agent nodes (all of
    # which need per-turn bound tools) — a static module-level agent here
    # was a harmless inconsistency, not a bug, but this keeps the pattern
    # uniform and makes get_llm() easier to reason about/test in isolation.
    agent = create_react_agent(
        model=get_llm(),
        tools=[search_product_catalog, web_search_specs],
        prompt=SystemMessage(content=SYSTEM_PROMPT),
    )
    result = agent.invoke({"messages": state["messages"]})
    # create_react_agent returns the full message list; we only want the
    # new AI message(s) it appended, since `messages` uses the add_messages
    # reducer and would otherwise duplicate history.
    new_messages = result["messages"][len(state["messages"]):]
    return {"messages": new_messages}
