"""Tests for document chunking."""

import pytest
from langchain_core.documents import Document

from app.ingestion.chunking import split_documents


def test_split_documents_creates_chunks_with_metadata():
    document = Document(
        page_content=("This is a test sentence. " * 100),
        metadata={"source": "sample.txt"},
    )

    chunks = split_documents(
        [document],
        chunk_size=100,
        chunk_overlap=20,
    )

    assert len(chunks) > 1
    assert all(len(chunk.page_content) <= 100 for chunk in chunks)
    assert all(chunk.metadata["source"] == "sample.txt" for chunk in chunks)
    assert all("chunk_id" in chunk.metadata for chunk in chunks)
    assert all("chunk_index" in chunk.metadata for chunk in chunks)


def test_split_documents_rejects_empty_input():
    with pytest.raises(ValueError, match="No documents"):
        split_documents([])


def test_split_documents_rejects_invalid_overlap():
    document = Document(page_content="Example text.")

    with pytest.raises(ValueError, match="smaller than chunk_size"):
        split_documents(
            [document],
            chunk_size=100,
            chunk_overlap=100,
        )


def test_split_documents_rejects_zero_chunk_size():
    document = Document(page_content="Example text.")

    with pytest.raises(ValueError, match="greater than zero"):
        split_documents([document], chunk_size=0)
