"""
Thin wrapper around chromadb: creates/opens the local persistent
collection and exposes add/query helpers used by ingest and query.

Planned responsibilities:
- Open a persistent Chroma client pointed at CHROMA_DIR.
- Get-or-create the collection named in config.COLLECTION_NAME.
- add_chunks(chunks): embed + store chunks with their metadata.
- search(query_text, n_results): return the top matching chunks with
  metadata (company, section, filing_date) so callers can cite them.
"""


def get_collection():
    """Placeholder. Will return a chromadb collection ready to use."""
    raise NotImplementedError("Vector store setup comes after the loader/chunker.")
