"""Create and load the local FAISS vector index."""

from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from app.rag.embeddings import get_embeddings


DEFAULT_INDEX_PATH = Path("vectorstore/faiss_index")


def create_vector_store(
    chunks: list[Document],
    index_path: str | Path = DEFAULT_INDEX_PATH,
) -> FAISS:
    """Embed chunks, build a FAISS index, and persist it."""
    if not chunks:
        raise ValueError("Cannot create an index from zero chunks.")

    path = Path(index_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    vector_store = FAISS.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
    )

    # Persist both the vector index and its document metadata for later retrieval.
    vector_store.save_local(str(path))

    print(f"[SAVED] FAISS index: {path.resolve()}")
    print(f"[SAVED] Indexed chunks: {len(chunks)}")

    return vector_store


def load_vector_store(
    index_path: str | Path = DEFAULT_INDEX_PATH,
) -> FAISS:
    """Load an existing FAISS index created by this application."""
    path = Path(index_path)

    if not (path / "index.faiss").is_file():
        raise FileNotFoundError(
            f"FAISS index not found at {path}. "
            "Run scripts/ingest_documents.py first."
        )

    if not (path / "index.pkl").is_file():
        raise FileNotFoundError(
            f"FAISS metadata file not found at {path}."
        )

    # FAISS metadata uses pickle; only load indexes generated and trusted locally.
    return FAISS.load_local(
        str(path),
        get_embeddings(),
        allow_dangerous_deserialization=True,
    )
