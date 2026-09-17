"""
Command-line entry point for asking questions once the database is
built.

Usage (once implemented):
    python scripts/ask.py "What are Apple's main supply chain risks?"
"""

import sys

from app.query import ask


def main():
    if len(sys.argv) < 2:
        print('Usage: python scripts/ask.py "your question here"')
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    result = ask(question)
    print(result)


if __name__ == "__main__":
    main()
