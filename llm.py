"""
Single place where we instantiate the LLM client.
All agent nodes import get_llm() from here rather than constructing
ChatGoogleGenerativeAI themselves — keeps provider-swapping to one function.
"""

import logging
import warnings

from langchain_google_genai import ChatGoogleGenerativeAI
from config import settings

# gemini-3.5-flash-lite ignores temperature/sampling params entirely and
# warns every call to say so — harmless, but drowns out real output.
warnings.filterwarnings("ignore", message=".*uses fixed sampling defaults")
# Informational nag about using generate_content directly instead of
# Chat.send_message; doesn't apply to how langchain drives the SDK.
logging.getLogger("google_genai.models").setLevel(logging.ERROR)


def get_llm(temperature: float | None = None) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key,
        temperature=temperature if temperature is not None else settings.llm_temperature,
    )
