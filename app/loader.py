"""
Loads raw 10-K filings from data/ and splits each one into labeled
sections (Business, Risk Factors, MD&A, Financial Statements).

How section detection works
----------------------------
SEC filings prepared with inline XBRL (the format EDGAR requires today)
mark each "Item" heading as bold text whose content starts immediately
with "Item N. <Title>", e.g.:

    <span style="...font-weight:700...">Item 1A. Risk Factors</span>

This is different from two other places "Item 1A" text shows up in the
same document: the clickable table of contents (where the text sits
inside an <a> tag, not directly in the span) and inline cross-references
in body text (e.g. "as discussed in Item 1A. Risk Factors"), which sit in
the middle of a sentence rather than at the start of a bold span. Requiring
"Item" to be the first text in a bold span filters out both.

Some filings also state "Item 8. Financial Statements" twice: once as a
short pointer ("see the F-pages"), and once at the real financial
statements later in the document. When a section's Item number appears
more than once, we keep whichever occurrence has the most text after it,
since the placeholder is always short.

This approach is tuned against the sample filing in data/VRT/. Other
filers' typesetting may differ slightly; if a filing yields far fewer
matches than expected, that's the first thing to check.
"""

import re
from pathlib import Path

from bs4 import BeautifulSoup

from app.config import DATA_DIR, SECTION_ITEM_MAP

# Matches a bold ("Item heading") span whose text starts with "Item N."
# Captures the item number (e.g. "1A") and the title text that follows.
ITEM_HEADER_RE = re.compile(
    r'<span style="[^"]*font-weight:700[^"]*">\s*Item\s+(\d+[A-Za-z]?)\.\s*([^<]*)</span>',
    re.IGNORECASE,
)


def _find_item_headers(html: str):
    """Return a list of (item_number, title, header_end_pos) in document order."""
    return [
        (m.group(1).upper(), m.group(2).strip(), m.end())
        for m in ITEM_HEADER_RE.finditer(html)
    ]


def _extract_metadata(html: str, fallback_ticker: str):
    """Pull company name/ticker/fiscal year from the filing's XBRL tags."""

    def first_tag_value(tag_name):
        m = re.search(rf'name="dei:{tag_name}"[^>]*>([^<]*)<', html)
        return m.group(1).strip() if m and m.group(1).strip() else None

    return {
        "company": first_tag_value("EntityRegistrantName") or fallback_ticker,
        "ticker": first_tag_value("TradingSymbol") or fallback_ticker,
        "fiscal_year": first_tag_value("DocumentFiscalYearFocus"),
    }


def _html_to_text(html_fragment: str) -> str:
    """Convert an HTML fragment to readable plain text."""
    # "html.parser" (not "lxml") because our fragments start mid-document,
    # right after a </span> we sliced on. lxml's stricter parser discards
    # everything when a fragment opens with a stray closing tag; the
    # built-in parser handles that leniently.
    soup = BeautifulSoup(html_fragment, "html.parser")
    text = soup.get_text(separator="\n")
    # Collapse the runs of blank lines/whitespace that come from dense
    # nested <div>/<span> markup, without losing paragraph breaks.
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def parse_filing(path: Path):
    """
    Parse one filing HTML file into a list of section records:
    {company, ticker, fiscal_year, section, text}

    Only the sections listed in config.SECTION_ITEM_MAP are extracted.
    """
    html = path.read_text(encoding="utf-8", errors="ignore")
    ticker = path.parent.name
    metadata = _extract_metadata(html, fallback_ticker=ticker)

    headers = _find_item_headers(html)
    if not headers:
        raise ValueError(
            f"No 'Item N.' section headers found in {path}. "
            "This filing's HTML structure may not match what loader.py expects "
            "(see the module docstring)."
        )

    records = []
    for section_name, item_number in SECTION_ITEM_MAP.items():
        # A section's Item number may appear more than once (e.g. a short
        # pointer to Item 8 followed by the real content later). Keep the
        # occurrence with the most following text.
        candidates = [h for h in headers if h[0] == item_number]
        if not candidates:
            continue

        best_start = None
        best_length = -1
        for _, _, header_end in candidates:
            next_starts = [h[2] for h in headers if h[2] > header_end]
            section_end = min(next_starts) if next_starts else len(html)
            length = section_end - header_end
            if length > best_length:
                best_length = length
                best_start = header_end
                best_end = section_end

        section_html = html[best_start:best_end]
        text = _html_to_text(section_html)

        records.append(
            {
                "company": metadata["company"],
                "ticker": metadata["ticker"],
                "fiscal_year": metadata["fiscal_year"],
                "section": section_name,
                "text": text,
            }
        )

    return records


def load_filings():
    """
    Walk data/<TICKER>/*.htm* and parse every filing found.
    Returns a flat list of section records (see parse_filing).
    """
    records = []
    for filing_path in sorted(DATA_DIR.glob("*/*.htm*")):
        records.extend(parse_filing(filing_path))
    return records


if __name__ == "__main__":
    # Quick manual check: python -m app.loader
    for record in load_filings():
        preview = record["text"][:120].replace("\n", " ")
        print(
            f"{record['ticker']} FY{record['fiscal_year']} | {record['section']} "
            f"| {len(record['text'])} chars | {preview}..."
        )
