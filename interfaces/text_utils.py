"""
Shared helper for I/O layers that read an AIMessage back out of the graph.
No side effects at import time (unlike chat_app.py, a Streamlit script), so
chat_app.py, voice_app.py, and api/routers/chat.py can all import this
directly instead of each keeping their own copy.
"""


def extract_text(content) -> str:
    """AIMessage.content can be a plain string or a list of content blocks
    (e.g. [{'type': 'text', 'text': '...'}]) depending on the model backend.
    Normalize to the plain text the user should see/hear."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)
