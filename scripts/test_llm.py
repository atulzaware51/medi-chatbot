"""Verify that Medibot can call its hosted LLM."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag.llm_service import get_llm


def main():
    print("Testing Medibot LLM connection...")

    llm = get_llm()
    response = llm.invoke(
        "Reply with exactly this text: Medibot LLM connection successful."
    )

    print("\nLLM RESPONSE")
    print("=" * 40)
    print(response.content)
    print("\nLLM API test completed.")


if __name__ == "__main__":
    main()
