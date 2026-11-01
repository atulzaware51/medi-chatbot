"""Manually test Medibot semantic retrieval."""

import sys
from pathlib import Path

# Add the Medibot project root to Python's import path.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag.retriever import search_knowledge_base


def main():
    query = "What is Medibot designed to do?"
    results = search_knowledge_base(query, k=3)

    print("\nMEDIBOT RETRIEVAL TEST")
    print("=" * 50)
    print(f"Query: {query}\n")

    if not results:
        print("No relevant passages were returned.")
        return

    for result in results:
        print(f"Rank: {result['rank']}")
        print(f"Source: {result['source']}")
        print(f"Page: {result['page']}")
        print("Content:")
        print(result["content"])
        print("-" * 50)


if __name__ == "__main__":
    main()
