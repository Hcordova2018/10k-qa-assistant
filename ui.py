"""
A small web UI on top of app.query.ask().

Run from the project folder:
    .venv\\Scripts\\streamlit run ui.py

Streamlit turns this script into a local web page (it opens in your
browser at http://localhost:8501). One thing to know about how it works:
Streamlit re-runs this whole script top to bottom every time you interact
with the page — typing, clicking, changing a filter. That's why the
question sits in a form (nothing happens until you press Ask) and the
last answer is kept in st.session_state, so each Claude call only happens
once per question instead of on every click.

All the real work still lives in app/: this file only collects input and
displays what ask() returns.
"""

import anthropic
import streamlit as st

from app.config import SECTIONS
from app.query import ask
from app.vectorstore import list_companies

ALL = "All"

st.set_page_config(page_title="10-K Q&A", page_icon="📄")
st.title("10-K Q&A")
st.caption(
    "Ask questions about the stored 10-K filings. Answers come only from "
    "the filings, and every claim is cited to its company and section."
)


@st.cache_data
def _companies():
    return list_companies()


def _md(text: str) -> str:
    # Streamlit renders $...$ as math, which would mangle dollar figures
    # like "$15.0 billion"; escaping the $ keeps them as plain text.
    return text.replace("$", "\\$")


companies = _companies()
if not companies:
    st.warning("No filings stored yet. Run `python scripts/ingest.py` first.")
    st.stop()

with st.form("ask"):
    question = st.text_area(
        "Question",
        placeholder="e.g. What supply chain risks does the company report?",
    )
    col1, col2 = st.columns(2)
    ticker = col1.selectbox(
        "Company",
        [ALL] + [t for t, _ in companies],
        format_func=lambda t: t if t == ALL else f"{dict(companies)[t]} ({t})",
    )
    section = col2.selectbox("Section", [ALL] + SECTIONS)
    submitted = st.form_submit_button("Ask", type="primary")

if submitted and question.strip():
    # Turn the dropdowns into a Chroma metadata filter. Two conditions
    # have to be combined with $and; one can be passed on its own.
    conditions = []
    if ticker != ALL:
        conditions.append({"ticker": ticker})
    if section != ALL:
        conditions.append({"section": section})
    where = None
    if len(conditions) == 1:
        where = conditions[0]
    elif conditions:
        where = {"$and": conditions}

    with st.spinner("Searching the filings and asking Claude..."):
        try:
            st.session_state.result = ask(question.strip(), where=where)
            st.session_state.question = question.strip()
        except (anthropic.AuthenticationError, TypeError) as e:
            # Same check as scripts/ask.py: TypeError means no credentials.
            if isinstance(e, TypeError) and "authentication" not in str(e):
                raise
            st.error(
                "Couldn't authenticate with the Anthropic API. Set "
                "ANTHROPIC_API_KEY in the terminal before starting the UI "
                "(see README), then restart it."
            )
            st.stop()
        except anthropic.APIError as e:
            st.error(f"The Anthropic API returned an error: {e}")
            st.stop()

result = st.session_state.get("result")
if result:
    st.subheader(st.session_state.question)
    st.markdown(_md(result["answer"]))

    if result["sources"]:
        st.markdown("#### Sources")
        for source in result["sources"]:
            with st.expander(f"[{source['n']}] {source['label']}"):
                for quote in source["quotes"]:
                    st.markdown(f"> {_md(' '.join(quote.split()))}")
                st.caption(f"Chunk {source['chunk_index']}")

    # Useful for learning how retrieval behaves: everything that was sent
    # to Claude, closest first, whether or not it ended up being cited.
    with st.expander(f"All {len(result['retrieved'])} retrieved passages"):
        for chunk in result["retrieved"]:
            st.markdown(
                f"**{chunk['ticker']} FY{chunk['fiscal_year']} · "
                f"{chunk['section']} · chunk {chunk['chunk_index']}** "
                f"(distance {chunk['distance']:.3f})"
            )
            st.text(" ".join(chunk["text"].split())[:500] + "...")
