"""
Command-line entry point: reads filings from data/, chunks them by
section, embeds them, and stores them in the local Chroma database.

Usage:
    python scripts/ingest.py

Rebuilds the collection from scratch each run, so the database always
matches exactly what's in data/.
"""

import sys
from pathlib import Path

# Let `python scripts/ingest.py` find the app package in the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import chunker, loader, vectorstore  # noqa: E402


def main():
    records = loader.load_filings()
    chunks = chunker.chunk_filings(records)
    filings = {(r["ticker"], r["fiscal_year"]) for r in records}
    print(f"Loaded {len(filings)} filing(s), {len(chunks)} chunks. Embedding...")

    vectorstore.reset_collection()
    count = vectorstore.add_chunks(chunks)
    print(f"Done. The database now holds {count} chunks.")


if __name__ == "__main__":
    main()
