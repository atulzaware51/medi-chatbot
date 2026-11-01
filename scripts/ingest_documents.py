
"""Build Medibot's local knowledge base from PDF and TXT files."""

import os
import sys
from pathlib import Path

# Resolve the Medibot project root.
ROOT = Path(__file__).resolve().parents[1]

# Allow Python to import the app package when this script is run directly.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from app.ingestion.chunking import split_documents
from app.ingestion.document_loader import load_documents
from app.rag.vector_store import create_vector_store


load_dotenv(ROOT / ".env")


def main() -> None:
    """Run the full document ingestion pipeline."""
    data_dir = ROOT / os.getenv("DATA_DIR", "data/raw")
    index_path = ROOT / os.getenv(
        "VECTORSTORE_DIR",
        "vectorstore/faiss_index",
    )

    print("=" * 60)
    print("MEDIBOT - DOCUMENT INGESTION")
    print("=" * 60)
    print(f"Project root:    {ROOT}")
    print(f"Input directory: {data_dir}")
    print(f"Vector index:    {index_path}")

    documents = load_documents(data_dir)
    print(f"\nExtracted documents/pages: {len(documents)}")

    chunks = split_documents(
        documents,
        chunk_size=800,
        chunk_overlap=120,
    )
    print(f"Created chunks: {len(chunks)}")

    create_vector_store(chunks, index_path)

    print("\nSUCCESS: Knowledge base created.")


if __name__ == "__main__":
    main()
