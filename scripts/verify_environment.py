"""Verify the Medibot Phase 1 environment."""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_MODULES = [
    "langchain",
    "langchain_core",
    "langchain_community",
    "langchain_text_splitters",
    "langgraph",
    "langchain_groq",
    "langchain_mistralai",
    "langchain_huggingface",
    "sentence_transformers",
    "faiss",
    "pypdf",
    "langgraph.checkpoint.sqlite",
    "fastapi",
    "uvicorn",
    "streamlit",
    "requests",
    "dotenv",
    "pytest",
    "httpx",
]


def main():
    print("=" * 55)
    print("MEDIBOT - PHASE 1 ENVIRONMENT VERIFICATION")
    print("=" * 55)

    print(f"Python executable: {sys.executable}")
    print(f"Python version:   {sys.version.split()[0]}")
    print(f"Project root:     {ROOT}")

    if sys.version_info[:2] != (3, 12):
        print("WARNING: This project is configured for Python 3.12.")

    failures = []

    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
            print(f"[PASS] {module_name}")
        except Exception as exc:
            failures.append((module_name, str(exc)))
            print(f"[FAIL] {module_name}: {exc}")

    required_files = [
        "requirements.txt",
        ".env",
        ".env.example",
        ".gitignore",
    ]

    print("\nProject configuration:")
    for relative_path in required_files:
        path = ROOT / relative_path
        if path.is_file():
            print(f"[PASS] {relative_path}")
        else:
            failures.append((relative_path, "File is missing"))
            print(f"[FAIL] {relative_path}")

    print("\n" + "=" * 55)

    if failures:
        print(f"FAILED: {len(failures)} verification issue(s).")
        for name, error in failures:
            print(f"- {name}: {error}")
        return 1

    print("SUCCESS: All Phase 1 checks passed.")
    print("The environment is ready for Phase 2.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
