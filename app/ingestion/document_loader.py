"""Load supported documents and preserve source metadata."""

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document


SUPPORTED_EXTENSIONS = {".pdf", ".txt"}


def load_document(file_path: str | Path) -> list[Document]:
    """Load one PDF or TXT file into LangChain Document objects."""
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Document not found: {path}")

    suffix = path.suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {suffix}. "
            "Supported types are PDF and TXT."
        )

    if suffix == ".pdf":
        documents = PyPDFLoader(str(path)).load()
    else:
        documents = TextLoader(
            str(path),
            encoding="utf-8",
            autodetect_encoding=True,
        ).load()

    cleaned_documents = []

    for document in documents:
        text = document.page_content.strip()

        # Ignore empty pages rather than indexing blank content.
        if not text:
            continue

        document.page_content = text
        # Store a filename (not an absolute path) so later citations identify the source safely.
        document.metadata["source"] = path.name
        cleaned_documents.append(document)

    return cleaned_documents


def load_documents(directory: str | Path) -> list[Document]:
    """Load every supported PDF and TXT file in a directory."""
    folder = Path(directory)

    if not folder.exists():
        raise FileNotFoundError(
            f"Document directory does not exist: {folder}"
        )

    if not folder.is_dir():
        raise NotADirectoryError(
            f"Expected a directory, received: {folder}"
        )

    files = sorted(
        path
        for path in folder.iterdir()
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not files:
        raise FileNotFoundError(
            f"No PDF or TXT files found in: {folder}"
        )

    documents = []

    for file_path in files:
        loaded = load_document(file_path)
        documents.extend(loaded)

        print(
            f"[LOADED] {file_path.name}: "
            f"{len(loaded)} non-empty page/document(s)"
        )

    if not documents:
        raise ValueError(
            "The supported files were found, but no readable text was extracted."
        )

    return documents
