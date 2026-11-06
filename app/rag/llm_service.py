"""Hosted LLM service for Medibot."""

import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_groq import ChatGroq

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)


@lru_cache(maxsize=1)
def get_llm():
    """Create and cache the configured Groq chat model."""
    # Fail explicitly for missing or unsupported configuration instead of silently
    # returning an unconfigured model to the answer-generation path.
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()

    if provider != "groq":
        raise ValueError(
            f"Unsupported LLM provider: {provider!r}. "
            "This service currently supports 'groq'."
        )

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "").strip()

    if not api_key:
        raise ValueError("GROQ_API_KEY is missing from the .env configuration.")

    if not model:
        raise ValueError("GROQ_MODEL is missing from the .env configuration.")

    # Reuse a deterministic, bounded-retry client for all answers in this process.
    return ChatGroq(
        model=model,
        api_key=api_key,
        temperature=0,
        max_retries=2,
        timeout=30,
    )
