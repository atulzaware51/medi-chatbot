
"""Unit tests for Medibot's document retriever."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from app.rag.retriever import (
    get_max_distance,
    retrieve_documents,
    search_knowledge_base,
)


def make_document(content: str, source: str = "guide.txt") -> Document:
    """Create a sample document for testing."""
    return Document(
        page_content=content,
        metadata={
            "source": source,
            "page": 1,
            "chunk_id": "chunk-1",
        },
    )


def test_retrieve_documents_returns_results_within_threshold():
    relevant = make_document("Medibot uses document retrieval.")
    irrelevant = make_document("Unrelated information.")

    fake_store = MagicMock()
    fake_store.similarity_search_with_score.return_value = [
        (relevant, 0.5),
        (irrelevant, 1.8),
    ]

    with patch(
        "app.rag.retriever.load_vector_store",
        return_value=fake_store,
    ):
        results = retrieve_documents(
            query="What is Medibot?",
            max_distance=1.2,
        )

    assert results == [relevant]
    fake_store.similarity_search_with_score.assert_called_once_with(
        query="What is Medibot?",
        k=4,
    )


def test_retrieve_documents_accepts_result_at_threshold():
    document = make_document("Matching content.")
    fake_store = MagicMock()
    fake_store.similarity_search_with_score.return_value = [
        (document, 1.2),
    ]

    with patch(
        "app.rag.retriever.load_vector_store",
        return_value=fake_store,
    ):
        results = retrieve_documents(
            query="matching content",
            max_distance=1.2,
        )

    assert results == [document]


def test_retrieve_documents_rejects_empty_query():
    with pytest.raises(ValueError, match="Query cannot be empty"):
        retrieve_documents(query="   ")


def test_retrieve_documents_rejects_invalid_k():
    with pytest.raises(ValueError, match="k must be at least 1"):
        retrieve_documents(query="test", k=0)


def test_get_max_distance_rejects_non_numeric_value(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_MAX_DISTANCE", "invalid")

    with pytest.raises(ValueError, match="valid number"):
        get_max_distance()


def test_get_max_distance_rejects_negative_value(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_MAX_DISTANCE", "-1")

    with pytest.raises(ValueError, match="cannot be negative"):
        get_max_distance()


def test_search_knowledge_base_formats_results():
    document = make_document("Medibot is an educational chatbot.")

    with patch(
        "app.rag.retriever.retrieve_documents",
        return_value=[document],
    ):
        results = search_knowledge_base(
            query="What is Medibot?",
            k=4,
        )

    assert results == [
        {
            "rank": 1,
            "content": "Medibot is an educational chatbot.",
            "source": "guide.txt",
            "page": 1,
            "chunk_id": "chunk-1",
        }
    ]
