
"""Retrieve relevant source passages from the FAISS knowledge base."""

import os
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from app.rag.vector_store import (
    DEFAULT_INDEX_PATH,
    load_vector_store,
)


def get_max_distance() -> float:
    """Read the maximum accepted FAISS distance from the environment."""
    value = os.getenv("RETRIEVAL_MAX_DISTANCE", "1.2")

    try:
        distance = float(value)
    except ValueError as exc:
        raise ValueError(
            "RETRIEVAL_MAX_DISTANCE must be a valid number."
        ) from exc

    if distance < 0:
        raise ValueError("RETRIEVAL_MAX_DISTANCE cannot be negative.")

    return distance


def retrieve_documents(
    query: str,
    k: int = 4,
    index_path: str | Path = DEFAULT_INDEX_PATH,
    max_distance: float | None = None,
) -> list[Document]:
    """Return document chunks whose FAISS distances pass the threshold."""
    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    if k < 1:
        raise ValueError("k must be at least 1.")

    if max_distance is None:
        max_distance = get_max_distance()

    if max_distance < 0:
        raise ValueError("max_distance cannot be negative.")

    vector_store = load_vector_store(index_path)

    scored_documents = vector_store.similarity_search_with_score(
        query=query.strip(),
        k=k,
    )

    # FAISS returns nearest candidates first; discard weak matches rather than
    # padding the answer context up to k with irrelevant passages.
    return [
        document
        for document, score in scored_documents
        if float(score) <= max_distance
    ]


def search_knowledge_base(
    query: str,
    k: int = 4,
    index_path: str | Path = DEFAULT_INDEX_PATH,
    max_distance: float | None = None,
) -> list[dict[str, Any]]:
    """Return relevant passages in an API-friendly format."""
    documents = retrieve_documents(
        query=query,
        k=k,
        index_path=index_path,
        max_distance=max_distance,
    )

    results = []

    # Preserve the retrieval order so citation labels follow relevance rank.
    for rank, document in enumerate(documents, start=1):
        results.append(
            {
                "rank": rank,
                "content": document.page_content,
                "source": document.metadata.get("source", "unknown"),
                "page": document.metadata.get("page"),
                "chunk_id": document.metadata.get("chunk_id"),
            }
        )

    return results
