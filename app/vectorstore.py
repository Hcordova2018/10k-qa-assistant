"""
Thin wrapper around chromadb: creates/opens the local persistent
collection and exposes add/search helpers used by ingest and query.

What embeddings are doing here
-------------------------------
An embedding model turns a piece of text into a list of numbers (a
"vector") — here, 384 numbers per chunk. The model was trained so that
texts with similar *meaning* end up with vectors pointing in similar
directions, even when they share no words. "Supply chain disruptions"
and "shortages of components from our vendors" land close together;
"supply chain disruptions" and "share repurchase program" land far apart.

That gives us search by meaning instead of by keyword:

1. At ingest time, every chunk is embedded once and its vector is stored
   in Chroma next to the chunk text and its metadata (company, section...).
2. At question time, the question is embedded with the *same* model, and
   Chroma finds the stored vectors closest to it. Those chunks are the
   ones most likely to talk about what the question is asking.

"Closest" is measured with cosine distance: 0 means the two vectors point
the same way (very similar meaning), larger means less related. The
absolute numbers aren't meaningful on their own — what matters is the
ranking, i.e. which chunks are closer than others.

Which model?
------------
We use Chroma's built-in default, all-MiniLM-L6-v2. It's small (~80 MB),
runs on the CPU via onnxruntime, and needs no API key — so the "everything
runs locally" promise holds. The first run downloads the model to
~/.cache/chroma; after that it works offline. The one rule that matters:
chunks and questions must be embedded by the same model, since vectors
from different models aren't comparable. If we ever switch models, the
collection has to be rebuilt (reset_collection() + add_chunks()).
"""

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from app.config import CHROMA_DIR, COLLECTION_NAME

# Chroma caps how many records one add/upsert call can take, so large
# ingests are sent in batches of this size.
_BATCH_SIZE = 256


def _client():
    # PersistentClient stores everything on disk under CHROMA_DIR, so the
    # database survives between runs — no server process needed.
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection():
    """Open (or create on first use) the collection all filings live in."""
    return _client().get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=DefaultEmbeddingFunction(),
        # Rank by cosine distance (direction of the vectors) rather than
        # Chroma's default squared-L2 — the usual choice for text embeddings.
        configuration={"hnsw": {"space": "cosine"}},
    )


def reset_collection():
    """Delete the collection so the next get_collection() starts empty."""
    client = _client()
    if COLLECTION_NAME in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION_NAME)


def _chunk_id(chunk: dict) -> str:
    # A stable ID built from what identifies a chunk, so re-ingesting the
    # same filing overwrites its chunks instead of storing duplicates.
    return (
        f"{chunk['ticker']}_{chunk['fiscal_year']}_"
        f"{chunk['section']}_{chunk['chunk_index']}"
    )


def add_chunks(chunks):
    """
    Embed and store chunk records (as produced by chunker.chunk_filings).

    We hand Chroma the raw text; because the collection has an embedding
    function attached, Chroma runs each chunk through the model and stores
    the resulting vector alongside the text and metadata.
    """
    collection = get_collection()
    for start in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[start : start + _BATCH_SIZE]
        collection.upsert(
            ids=[_chunk_id(c) for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[
                {
                    # Chroma metadata values can't be None, so a missing
                    # fiscal year (loader couldn't find the tag) becomes "".
                    "company": c["company"],
                    "ticker": c["ticker"],
                    "fiscal_year": c["fiscal_year"] or "",
                    "section": c["section"],
                    "chunk_index": c["chunk_index"],
                }
                for c in batch
            ],
        )
    return collection.count()


def list_companies():
    """Return (ticker, company) pairs for every filing in the collection."""
    metadatas = get_collection().get(include=["metadatas"])["metadatas"]
    return sorted({(m["ticker"], m["company"]) for m in metadatas})


def search(query_text: str, n_results: int = 5, where: dict | None = None):
    """
    Return the n_results chunks whose meaning is closest to query_text.

    `where` optionally filters on metadata before ranking, e.g.
    {"section": "Risk Factors"} or {"ticker": "VRT"}.

    Each result is a dict with the chunk's text, its metadata (for
    citations), and its cosine distance to the query (lower = closer).
    """
    results = get_collection().query(
        query_texts=[query_text],
        n_results=n_results,
        where=where,
    )
    # query() accepts several questions at once and returns one list per
    # question; we only sent one, hence the [0]s.
    return [
        {"text": text, "distance": distance, **metadata}
        for text, metadata, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]


if __name__ == "__main__":
    # Quick manual check: python -m app.vectorstore
    # Rebuilds the collection from data/, then runs a few test searches.
    from app.chunker import chunk_filings
    from app.loader import load_filings

    chunks = chunk_filings(load_filings())
    reset_collection()
    print(f"Embedding and storing {len(chunks)} chunks...")
    print(f"Collection now holds {add_chunks(chunks)} chunks.\n")

    # Questions worded differently from the filing text on purpose, to
    # show retrieval works on meaning rather than exact keyword matches.
    test_queries = [
        "What could go wrong with getting parts from suppliers?",
        "How did net sales change compared to the prior year?",
        "What products does the company sell and who buys them?",
    ]
    for q in test_queries:
        print(f"Q: {q}")
        for hit in search(q, n_results=3):
            snippet = " ".join(hit["text"].split())[:140]
            print(
                f"  [{hit['distance']:.3f}] {hit['ticker']} FY{hit['fiscal_year']} "
                f"{hit['section']} #{hit['chunk_index']}: {snippet}..."
            )
        print()
