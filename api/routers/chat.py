"""
Text chat endpoint — the HTTP equivalent of interfaces/chat_app.py's
message loop. Same graph, same invoke shape, same __interrupt__ handling;
only the transport differs.
"""

from fastapi import APIRouter, Depends, Request
from langchain_core.messages import AIMessage, HumanMessage

from interfaces.text_utils import extract_text

from api.schemas import ChatRequest
from api.session import SessionData, require_session

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
def chat(payload: ChatRequest, request: Request, session_data: SessionData = Depends(require_session)):
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": session_data.conversation_id}}
    graph_input = {
        "messages": [HumanMessage(content=payload.message)],
        "customer_id": session_data.customer_id,
        "conversation_id": session_data.conversation_id,
    }

    result = graph.invoke(graph_input, config=config)

    if "__interrupt__" in result:
        interrupt_payload = result["__interrupt__"][0].value
        reply = interrupt_payload.get("message", "You're being connected to a human agent.")
        return {"reply": reply, "escalated": True}

    last_ai = next((m for m in reversed(result["messages"]) if isinstance(m, AIMessage)), None)
    reply = extract_text(last_ai.content) if last_ai else "(no response)"
    return {"reply": reply, "escalated": False}
