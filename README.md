# 10-K Q&A Assistant

Ask plain-English questions about companies' SEC 10-K filings and get
answers where every claim is cited to the company, fiscal year and section
(Risk Factors, MD&A, etc.) it came from — with the exact quoted passage.

Built as a retrieval-augmented generation (RAG) pipeline: filings are split
by 10-K section, embedded locally and stored in [Chroma](https://www.trychroma.com/);
at question time the most relevant passages are retrieved and
[Claude](https://www.anthropic.com/claude) writes an answer grounded only
in them.

<!-- Screenshot: save one as docs/screenshot.png, then uncomment:
![The web UI answering a question about Vertiv's supply chain risks](docs/screenshot.png)
-->

## Example

```text
> python scripts/ask.py "What supply chain risks does Vertiv report?"

Vertiv's FY2025 filing describes its supply chain approach and several related risks:

- Part shortages and premium costs: Despite the diversification strategy, Vertiv
  may from time to time experience critical part shortages which may drive the
  need for additional spot buys at increased costs ...[1]
- Single-source suppliers: Certain materials or components come from
  single-source suppliers due to technology, availability, price, quality or
  other considerations ...[3]
  ...
This is relevant context given backlog grew to $15.0 billion as of December 31,
2025 from $7.2 billion a year earlier ...[4]

Sources:
  [1] Vertiv Holdings Co (VRT), FY2025, Business (chunk 15)
      "Despite this strategy, it is possible that we may from time to time experience critical part shortages ..."
  [3] Vertiv Holdings Co (VRT), FY2025, Risk Factors (chunk 15)
      "• Single-source suppliers - We obtain certain materials or components from single-source suppliers ..."
  [4] Vertiv Holdings Co (VRT), FY2025, Business (chunk 4)
      "Backlog Vertiv's estimated combined order backlog was $15.0 billion and $7.2 billion as of December 31, 2025 and 2024 ..."
```

## How it works

```
data/*.htm ──► load ──► chunk ──► embed + store ──► retrieve ──► Claude ──► cited answer
              (by 10-K   (~1500    (local model,    (closest     (answers only
               section)   chars)    Chroma)          passages)    from passages)
```

1. **Load** (`app/loader.py`) — parses each filing's HTML and splits it into
   its standard sections: Business (Item 1), Risk Factors (Item 1A), MD&A
   (Item 7) and Financial Statements (Item 8). Company, ticker and fiscal
   year are read from the filing's inline XBRL tags.
2. **Chunk** (`app/chunker.py`) — breaks long sections into ~1500-character
   chunks on paragraph boundaries, with a small overlap, and keeps the
   company/year/section tags on every chunk.
3. **Store** (`app/vectorstore.py`) — embeds each chunk and stores it in a
   local Chroma collection with its metadata.
4. **Query** (`app/query.py`) — embeds the question, retrieves the closest
   chunks (optionally filtered by company or section), and sends them to
   Claude, which answers using only those passages.

### Design decisions

- **Split by 10-K section, not arbitrary blocks.** Every chunk knows it came
  from, say, Vertiv's FY2025 Risk Factors, so citations are meaningful and
  searches can be narrowed to one section.
- **Local embeddings.** Chunks are embedded with all-MiniLM-L6-v2 running on
  the CPU through Chroma — free, no API key, and the filings never leave the
  machine to be indexed.
- **Citations from the API, not the prompt.** Each retrieved chunk is sent as
  a separate document with the Anthropic API's citations feature enabled, so
  every cited claim comes back attached to an exact quote from a real passage
  instead of relying on the model to write `[1]` markers correctly.
- **Answers only from the filings.** Claude is instructed to say when the
  retrieved passages don't contain the answer rather than filling gaps from
  general knowledge.
- **One core, two front ends.** The CLI and the web UI are thin layers over
  the same `app.query.ask()` function.

## Tech stack

Python · [Chroma](https://www.trychroma.com/) (vector store) ·
all-MiniLM-L6-v2 via onnxruntime (embeddings) · Anthropic API /
`claude-opus-5` (answers with citations) · Beautiful Soup (HTML parsing) ·
[Streamlit](https://streamlit.io/) (web UI)

## Getting started

### 1. Install

```powershell
git clone https://github.com/Hcordova2018/10k-qa-assistant.git
cd 10k-qa-assistant
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

> **Windows note:** the embedding model runs on `onnxruntime`, which needs a
> recent Microsoft Visual C++ runtime. If Python exits silently (or with
> "access violation") as soon as anything is embedded, install the latest
> [Visual C++ Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe).

### 2. Add filings

Download 10-K filings (the HTML version) from
[SEC EDGAR](https://www.sec.gov/edgar/search/) and put each one in a folder
named after its ticker:

```
data/
├── NKE/
│   └── nke-10k.htm
└── VRT/
    └── vrt-10k.html
```

Any filename ending in `.htm` or `.html` works. Filings aren't checked into
this repo — download your own.

### 3. Build the vector database

```powershell
python scripts/ingest.py
```

Re-run this whenever `data/` changes; it rebuilds the database from scratch.
The first run downloads the ~80 MB embedding model to `~/.cache/chroma`.

### 4. Set an Anthropic API key

Create a key in the [Claude Console](https://console.anthropic.com/settings/keys)
(if your organization uses workspaces, create it inside a workspace). Each
question costs on the order of a cent.

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."    # macOS/Linux: export ANTHROPIC_API_KEY=...
```

Never put the key in a file inside the project, where it could be committed.

### 5. Ask questions

From the command line:

```powershell
python scripts/ask.py "What supply chain risks does Vertiv report?"
```

Or in the browser, with dropdowns to narrow a question to one company or
section:

```powershell
streamlit run ui.py
```

The UI opens at http://localhost:8501. Each answer shows its sources as
expandable quotes, plus every passage retrieval found and its distance —
useful for seeing why an answer did or didn't cover something.

Each module can also be run on its own as a sanity check:
`python -m app.loader`, `python -m app.chunker`, `python -m app.vectorstore`.

## Project structure

```
10k-qa-assistant/
├── app/
│   ├── config.py         # Paths and constants shared by everything else
│   ├── loader.py         # Reads filings, splits into sections
│   ├── chunker.py        # Splits long sections into embeddable chunks
│   ├── vectorstore.py    # Wraps Chroma: add chunks, search chunks
│   └── query.py          # ask(question) -> answer + citations
├── scripts/
│   ├── ingest.py         # CLI: build the vector database from data/
│   └── ask.py            # CLI: ask a question
├── ui.py                 # Web UI (Streamlit)
├── data/                 # Your downloaded filings (not in git)
└── chroma_db/            # Generated vector database (not in git)
```

## Limitations

- **Four sections only.** Business, Risk Factors, MD&A and Financial
  Statements are indexed; other Items (e.g. Legal Proceedings, Executive
  Compensation) are skipped.
- **Section detection is tuned on inline-XBRL filings.** It looks for bold
  "Item N." headings; filers with unusual typesetting may need adjustments
  to `app/loader.py`.
- **The small embedding model is sensitive to wording.** "How much money did
  the company bring in?" retrieves worse passages than "How did net sales
  change?", because the filing says "net sales". Using the filing's own
  vocabulary gets better results.
- **Tables lose their structure.** Financial tables are flattened to text,
  so precise numeric questions work best when the MD&A narrative states the
  figure.

## License

[MIT](LICENSE)
