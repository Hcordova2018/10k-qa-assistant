"""
The simple query function this whole project is building toward:
take a natural-language question, retrieve the most relevant chunks
from the vector store, and return an answer with citations back to
the company and section each piece of evidence came from.

Planned responsibilities:
- Embed the user's question the same way chunks were embedded.
- Retrieve top-N matching chunks from vectorstore.search().
- Either (a) return the raw matching chunks with citations for a first
  pass with no LLM involved, or (b) pass them to an LLM as context and
  ask it to answer while citing (company, section) for each claim.
"""


def ask(question: str, n_results: int = 5):
    """Placeholder. Will return an answer plus a list of citations."""
    raise NotImplementedError("Query function is built once the vector store works.")
