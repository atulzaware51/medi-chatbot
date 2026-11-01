"""Tests for document loading."""

import pytest

from app.ingestion.document_loader import (
    load_document,
    load_documents,
)


def test_load_txt_preserves_source_metadata(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text(
        "Medibot is a document retrieval project.",
        encoding="utf-8",
    )

    documents = load_document(file_path)

    assert len(documents) == 1
    assert "document retrieval" in documents[0].page_content
    assert documents[0].metadata["source"] == "sample.txt"


def test_load_document_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_document(tmp_path / "missing.txt")


def test_load_document_rejects_unsupported_extension(tmp_path):
    file_path = tmp_path / "sample.csv"
    file_path.write_text("a,b", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file type"):
        load_document(file_path)


def test_load_documents_rejects_empty_directory(tmp_path):
    with pytest.raises(FileNotFoundError, match="No PDF or TXT"):
        load_documents(tmp_path)


def test_load_documents_reads_multiple_txt_files(tmp_path):
    (tmp_path / "first.txt").write_text(
        "First document.", encoding="utf-8"
    )
    (tmp_path / "second.txt").write_text(
        "Second document.", encoding="utf-8"
    )

    documents = load_documents(tmp_path)

    assert len(documents) == 2
    assert {
        document.metadata["source"] for document in documents
    } == {"first.txt", "second.txt"}
