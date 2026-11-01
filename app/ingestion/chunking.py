"""Split loaded documents into searchable text chunks."""

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_documents(
    documents: list[Document],
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[Document]:
    """Split documents and attach a stable ID within this batch."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap cannot be negative.")

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be smaller than chunk_size."
        )

    if not documents:
        raise ValueError("No documents were provided for chunking.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
        add_start_index=True,
    )

    chunks = splitter.split_documents(documents)
    cleaned_chunks = []

    for index, chunk in enumerate(chunks):
        chunk.page_content = chunk.page_content.strip()

        if not chunk.page_content:
            continue

        source = str(chunk.metadata.get("source", "unknown"))
        page = chunk.metadata.get("page", "na")

        chunk.metadata["chunk_index"] = index
        chunk.metadata["chunk_id"] = (
            f"{source}:page-{page}:chunk-{index}"
        )

        cleaned_chunks.append(chunk)

    if not cleaned_chunks:
        raise ValueError("Chunking produced no non-empty chunks.")

    return cleaned_chunks
