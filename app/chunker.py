"""
Turns section-labeled filing records (from loader.py) into chunks sized
for embedding, while preserving the metadata needed for citations.

Why chunk within a section at all? A section like Risk Factors can be
80,000+ characters — far too long to hand an embedding model as one
unit (embeddings get vaguer as inputs get longer, since one vector has to
summarize everything in it). So each section is broken into smaller
pieces, but every piece keeps the company/ticker/fiscal year/section
metadata from loader.py attached, so a citation always reads like
"Vertiv (VRT), FY2025, Risk Factors" rather than a bare chunk index.

How splitting works
--------------------
loader.py already produces text as one paragraph/line per line break
(each line came from a distinct HTML block element). We pack whole lines
into a chunk until adding the next one would exceed CHUNK_SIZE_CHARS,
then start a new chunk. A short tail of the previous chunk is carried
over as overlap, so context near a chunk boundary isn't lost entirely.

If a single line is itself longer than CHUNK_SIZE_CHARS (some paragraphs
in Risk Factors run long), it's split further by sentence, and as a last
resort by raw character count.
"""

import re

from app.config import CHUNK_OVERLAP_CHARS, CHUNK_SIZE_CHARS

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_long_line(line: str, size: int):
    """Break a single line that's longer than `size` into smaller pieces."""
    sentences = _SENTENCE_SPLIT_RE.split(line)
    pieces = []
    current = ""
    for sentence in sentences:
        if current and len(current) + 1 + len(sentence) > size:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)

    # A single sentence longer than `size` (rare, but possible in dense
    # financial text) gets hard-sliced as a last resort.
    final_pieces = []
    for piece in pieces:
        if len(piece) <= size:
            final_pieces.append(piece)
        else:
            final_pieces.extend(
                piece[i : i + size] for i in range(0, len(piece), size)
            )
    return final_pieces


def chunk_section(
    record: dict,
    chunk_size: int = CHUNK_SIZE_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
):
    """
    Split one section record (as produced by loader.parse_filing) into a
    list of chunk records: the same metadata, plus a "chunk_index" and
    the chunk's own "text" replacing the full section text.
    """
    lines = record["text"].split("\n")

    # Pre-split any individual line that's already too long on its own.
    normalized_lines = []
    for line in lines:
        if len(line) <= chunk_size:
            normalized_lines.append(line)
        else:
            normalized_lines.extend(_split_long_line(line, chunk_size))

    chunks_text = []
    current_lines = []
    current_len = 0

    for line in normalized_lines:
        if current_lines and current_len + len(line) > chunk_size:
            chunks_text.append("\n".join(current_lines))

            # Carry the tail of this chunk into the next one as overlap.
            overlap_lines = []
            overlap_len = 0
            for prev_line in reversed(current_lines):
                if overlap_len + len(prev_line) > overlap:
                    break
                overlap_lines.insert(0, prev_line)
                overlap_len += len(prev_line)
            current_lines = overlap_lines
            current_len = overlap_len

        current_lines.append(line)
        current_len += len(line)

    if current_lines:
        chunks_text.append("\n".join(current_lines))

    return [
        {
            "company": record["company"],
            "ticker": record["ticker"],
            "fiscal_year": record["fiscal_year"],
            "section": record["section"],
            "chunk_index": i,
            "text": chunk_text,
        }
        for i, chunk_text in enumerate(chunks_text)
    ]


def chunk_filings(records):
    """Apply chunk_section to a list of section records and flatten the result."""
    chunks = []
    for record in records:
        chunks.extend(chunk_section(record))
    return chunks


if __name__ == "__main__":
    # Quick manual check: python -m app.chunker
    from app.loader import load_filings

    chunks = chunk_filings(load_filings())
    print(f"Total chunks: {len(chunks)}\n")

    by_section = {}
    for c in chunks:
        by_section.setdefault(c["section"], []).append(c)

    for section, section_chunks in by_section.items():
        sizes = [len(c["text"]) for c in section_chunks]
        print(
            f"{section}: {len(section_chunks)} chunks, "
            f"avg {sum(sizes) // len(sizes)} chars, max {max(sizes)} chars"
        )
