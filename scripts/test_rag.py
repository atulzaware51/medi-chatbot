"""Test Medibot's end-to-end RAG answer service."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag.answer_service import ask_medibot


def main():
    question = "What is Medibot designed to do?"

    print("Testing Medibot RAG...")
    result = ask_medibot(question)

    print("\nQUESTION")
    print(result["question"])

    print("\nANSWER")
    print(result["answer"])

    print("\nSOURCES")
    for source in result["sources"]:
        print(
            f"[{source['id']}] {source['source']} "
            f"| Page: {source['page']} "
            f"| Chunk: {source['chunk_id']}"
        )

    if not result["sources"]:
        print("No sources were retrieved.")

    print("\nRAG test completed.")


if __name__ == "__main__":
    main()
