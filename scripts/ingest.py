"""
Command-line entry point: reads filings from data/, chunks them by
section, embeds them, and stores them in the local Chroma database.

Usage (once implemented):
    python scripts/ingest.py

This is a stub until loader.py, chunker.py, and vectorstore.py are
implemented.
"""

from app import loader, chunker, vectorstore  # noqa: F401  (used once implemented)


def main():
    raise NotImplementedError("Run this once the loader/chunker/vectorstore are built.")


if __name__ == "__main__":
    main()
