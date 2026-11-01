
"""Evaluate Medibot retrieval quality using labelled test queries."""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

VECTORSTORE_DIR = PROJECT_ROOT / os.getenv(
    "VECTORSTORE_DIR", "vectorstore/faiss_index"
)
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "4"))
CURRENT_THRESHOLD = float(os.getenv("RETRIEVAL_MAX_DISTANCE", "1.2"))

# Expected source filename, or None when the query should not match.
TEST_CASES = [
    ("What is a fracture or broken bone?", "medlineplus_fractures.txt"),
    ("What are common symptoms of a fracture?", "medlineplus_fractures.txt"),
    ("What is a stress fracture?", "medlineplus_fractures.txt"),
    ("What is osteoporosis?", "medlineplus_bone_health.txt"),
    ("Why is bone density important?", "medlineplus_bone_health.txt"),
    ("How do I evaluate medical source reliability?", "medibot_source_quality.txt"),
    ("Why should Medibot cite its sources?", "medibot_source_quality.txt"),
    ("What is Medibot designed to do?", "medibot_demo.txt"),
    ("What is the exact population of Mars?", None),
    ("Who won the 2024 Cricket World Cup?", None),
    ("How do I reverse a linked list in Python?", None),
    ("What is the capital of Japan?", None),
]


def main():
    if not VECTORSTORE_DIR.exists():
        raise FileNotFoundError(
            f"FAISS index not found: {VECTORSTORE_DIR}\n"
            "Run: python .\\scripts\\ingest_documents.py"
        )

    print("Loading embedding model and FAISS index...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vectorstore = FAISS.load_local(
        str(VECTORSTORE_DIR),
        embeddings,
        allow_dangerous_deserialization=True,
    )

    results = []

    print("\n" + "=" * 75)
    print("RETRIEVAL EVALUATION")
    print("=" * 75)

    for query, expected_source in TEST_CASES:
        matches = vectorstore.similarity_search_with_score(
            query, k=RETRIEVAL_K
        )

        # Keep the nearest result only if it meets the current threshold.
        accepted = [
            (doc, float(distance))
            for doc, distance in matches
            if float(distance) <= CURRENT_THRESHOLD
        ]

        nearest_source = (
            Path(accepted[0][0].metadata.get("source", "")).name
            if accepted else None
        )
        correct = (
            nearest_source == expected_source
            if expected_source is not None
            else nearest_source is None
        )

        results.append({
            "query": query,
            "expected": expected_source,
            "matches": matches,
            "nearest_source": nearest_source,
            "correct": correct,
        })

        print(f"\nQuery: {query}")
        print(f"Expected: {expected_source or 'NO MATCH'}")
        print(f"Nearest accepted source: {nearest_source or 'NO MATCH'}")
        print(f"Result: {'PASS' if correct else 'CHECK'}")

        if matches:
            doc, distance = matches[0]
            source = Path(doc.metadata.get("source", "unknown")).name
            print(f"Nearest raw distance: {float(distance):.4f}")
            print(f"Nearest raw source: {source}")
            print(f"Preview: {doc.page_content[:180].replace(chr(10), ' ')}")
        else:
            print("No vector results returned.")

    print("\n" + "=" * 75)
    passed = sum(item["correct"] for item in results)
    print(f"CURRENT THRESHOLD: {CURRENT_THRESHOLD}")
    print(f"CORRECT CASES: {passed}/{len(results)}")
    print("=" * 75)

    print("\nRaw nearest distances for threshold analysis:")
    for item in results:
        if item["matches"]:
            doc, distance = item["matches"][0]
            source = Path(doc.metadata.get("source", "unknown")).name
            print(
                f"{float(distance):.4f} | "
                f"{'EXPECTED MATCH' if item['expected'] else 'EXPECTED NO MATCH':18} | "
                f"{source:32} | {item['query']}"
            )

    print(
        "\nNote: this is a small preliminary test set. "
        "Do not treat its best threshold as a validated medical safety boundary."
    )


if __name__ == "__main__":
    main()
