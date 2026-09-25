"""
The query function this whole project is building toward: take a
natural-language question, retrieve the most relevant chunks from the
vector store, and have Claude answer from them with citations back to
the company, fiscal year and section each piece of evidence came from.

How it fits together (this pattern is called RAG, retrieval-augmented
generation):

1. Retrieve — vectorstore.search() embeds the question and returns the
   chunks closest in meaning (stage 3). Claude never sees the whole
   filing, only these few excerpts.
2. Generate — the excerpts are sent to Claude as separate "documents",
   each titled with its citation, e.g. "Vertiv Holdings Co (VRT), FY2025,
   Risk Factors". Claude is told to answer only from them.
3. Cite — we turn on the API's built-in citations feature. Instead of
   trusting Claude to write "[1]" markers itself, the API attaches to each
   sentence of the answer the exact passage it relied on and which
   document that passage came from. Because those quotes are pulled from
   the documents we sent, a citation can't point at text that isn't there.

Needs an Anthropic API key in the ANTHROPIC_API_KEY environment variable
(see README). Each question costs on the order of a cent.
"""

import anthropic

from app.vectorstore import search

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """\
You answer questions about companies' SEC 10-K filings for someone \
researching them. You are given excerpts retrieved from the filings; \
answer using only those excerpts. If they don't contain the answer, \
say so plainly rather than filling the gap from general knowledge. \
Be concise and specific: quote figures exactly as the filing states \
them, including units and the period they refer to."""


def _citation_label(chunk: dict) -> str:
    return (
        f"{chunk['company']} ({chunk['ticker']}), "
        f"FY{chunk['fiscal_year']}, {chunk['section']}"
    )


def ask(question: str, n_results: int = 8, where: dict | None = None):
    """
    Answer `question` from the stored filings.

    Returns a dict:
        answer    — the answer text, with [n] markers after cited claims
        sources   — one entry per [n]: citation label, chunk_index, and the
                    exact quoted passage(s) Claude relied on
        retrieved — every chunk that was sent to Claude, cited or not
                    (handy for seeing what retrieval found)

    `where` narrows retrieval by metadata, e.g. {"ticker": "VRT"}.
    """
    chunks = search(question, n_results=n_results, where=where)
    if not chunks:
        return {
            "answer": "No filings are stored yet — run scripts/ingest.py first.",
            "sources": [],
            "retrieved": [],
        }

    documents = [
        {
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": c["text"]},
            "title": _citation_label(c),
            "citations": {"enabled": True},
        }
        for c in chunks
    ]

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [*documents, {"type": "text", "text": question}],
            }
        ],
        # If Claude Opus 5's safety classifiers decline a request, the API
        # re-runs it on Anthropic's recommended fallback model instead of
        # returning a refusal. A 10-K question should never trip this; it's
        # a cheap safety net.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )

    if response.stop_reason == "refusal":
        return {
            "answer": "Claude declined to answer this question.",
            "sources": [],
            "retrieved": chunks,
        }

    # With citations on, the answer comes back split into several text
    # blocks; a block that makes a claim carries the passage(s) behind it.
    # Number each cited document the first time it appears, so sources
    # read [1], [2], ... in the order the answer uses them.
    answer_parts = []
    source_numbers = {}  # document_index -> [n]
    sources = []
    for block in response.content:
        if block.type != "text":
            continue
        answer_parts.append(block.text)
        markers = []
        for citation in block.citations or []:
            doc = citation.document_index
            if doc not in source_numbers:
                source_numbers[doc] = len(sources) + 1
                sources.append(
                    {
                        "n": source_numbers[doc],
                        "label": _citation_label(chunks[doc]),
                        "chunk_index": chunks[doc]["chunk_index"],
                        "quotes": [],
                    }
                )
            source = sources[source_numbers[doc] - 1]
            quote = citation.cited_text.strip()
            if quote not in source["quotes"]:
                source["quotes"].append(quote)
            marker = f"[{source_numbers[doc]}]"
            if marker not in markers:
                markers.append(marker)
        if markers:
            answer_parts.append("".join(markers))

    return {
        "answer": "".join(answer_parts).strip(),
        "sources": sources,
        "retrieved": chunks,
    }
