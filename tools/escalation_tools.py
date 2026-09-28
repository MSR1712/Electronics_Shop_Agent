"""
Escalation: asynchronous log + notify, NOT a real-time takeover. The DB row
is the source of truth for the support queue; Slack is a best-effort
notification layered on top — if Slack is down, the escalation still
exists and is queryable/assignable by a human.

SECURITY: like order_tools, customer_id is bound via a factory rather than
being an LLM-supplied argument.
"""

import json
import urllib.request

from langchain_core.tools import tool
from langgraph.types import interrupt

from config import settings
from db.models import Escalation, EscalationStatus
from db.session import get_session


def _notify_slack(customer_id: str, reason: str, escalation_id: int) -> None:
    if not settings.slack_webhook_url:
        print(f"[escalation] Slack not configured. Escalation #{escalation_id} logged only.")
        return

    payload = {
        "text": (
            f":rotating_light: New escalation #{escalation_id}\n"
            f"*Customer:* {customer_id}\n"
            f"*Reason:* {reason}"
        )
    }
    req = urllib.request.Request(
        settings.slack_webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        # Best-effort only — the DB row already exists as the source of truth.
        print(f"[escalation] Slack notify failed: {e}")


def make_escalation_tool(customer_id: str, conversation_id: str | None = None):
    """Returns [escalate_to_human] bound to the authenticated customer_id."""

    @tool
    def escalate_to_human(reason: str) -> str:
        """
        Hands off the conversation to a human support agent. Use this when
        the issue can't be resolved by product info, order tools, or
        policy lookup. `reason` should be a concise 2-4 sentence summary
        of the issue and what's already been tried.
        """
        with get_session() as session:
            escalation = Escalation(
                customer_id=customer_id,
                conversation_id=conversation_id,
                reason=reason,
                status=EscalationStatus.OPEN,
            )
            session.add(escalation)
            session.commit()
            session.refresh(escalation)
            escalation_id = escalation.id

        _notify_slack(customer_id, reason, escalation_id)

        # Pauses the graph; the interrupt payload is surfaced to whichever
        # I/O layer (chat/voice) is driving this run.
        interrupt(
            {
                "type": "human_handoff",
                "escalation_id": escalation_id,
                "message": (
                    "This has been passed to a member of our support team — "
                    "they'll follow up with you directly. Is there anything "
                    "else I can help with in the meantime?"
                ),
            }
        )

        return json.dumps({"success": True, "escalation_id": escalation_id, "status": "open"})

    return [escalate_to_human]
