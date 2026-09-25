"""
Command-line entry point for asking questions once the database is
built.

Usage:
    python scripts/ask.py "What supply chain risks does Vertiv report?"
"""

import sys
from pathlib import Path

# Let `python scripts/ask.py` find the app package in the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402

from app.query import ask  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print('Usage: python scripts/ask.py "your question here"')
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    try:
        result = ask(question)
    except (anthropic.AuthenticationError, TypeError) as e:
        # The SDK raises TypeError when no credentials are configured at
        # all, and AuthenticationError when the key is rejected.
        if isinstance(e, TypeError) and "authentication" not in str(e):
            raise
        print(
            "Couldn't authenticate with the Anthropic API. Set your key first:\n"
            '  $env:ANTHROPIC_API_KEY = "sk-ant-..."   (see README)'
        )
        sys.exit(1)

    print(result["answer"])
    if result["sources"]:
        print("\nSources:")
        for source in result["sources"]:
            print(f"  [{source['n']}] {source['label']} (chunk {source['chunk_index']})")
            for quote in source["quotes"]:
                snippet = " ".join(quote.split())
                if len(snippet) > 160:
                    snippet = snippet[:157] + "..."
                print(f'      "{snippet}"')


if __name__ == "__main__":
    main()
