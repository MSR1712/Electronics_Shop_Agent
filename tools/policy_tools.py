"""
Tool for the policy & support agent: semantic search over policy docs.

NOTE ON DATA PROVENANCE: returns/warranty/shipping/FAQ docs are LLM-generated
demo data (see data/generate_synthetic_data.py). Before production use,
replace data/policies/*.md with actual approved company documents and
re-run scripts/ingest_policies.py — do not let generated policy text reach
real customers.
"""

import json

from langchain_core.tools import tool

from rag.vectorstore import get_policy_vectorstore

MIN_RELEVANCE = 0.5


@tool
def search_policy(query: str, k: int = 3) -> str:
    """
    Semantic search over company policy documents: returns, warranty,
    shipping, and FAQ. Use this for any question about return windows,
    warranty coverage, shipping times/costs, or general company policy.
    Returns structured JSON, or {"found": false} if nothing relevant
    enough was found — in that case, say you don't have that policy
    information rather than guessing. Does NOT contain order-specific
    data — use get_order_status for that.
    """
    store = get_policy_vectorstore()
    results = store.similarity_search_with_relevance_scores(query, k=k)
    relevant = [(doc, score) for doc, score in results if score >= MIN_RELEVANCE]

    if not relevant:
        return json.dumps({"found": False, "reason": "no results above relevance threshold"})

    chunks = [
        {
            "source": doc.metadata.get("source", "unknown"),
            "text": doc.page_content,
            "relevance_score": round(score, 3),
        }
        for doc, score in relevant
    ]
    return json.dumps({"found": True, "chunks": chunks})
