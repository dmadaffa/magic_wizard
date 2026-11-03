"""Scryfall search for /improve-deck: compact result lines plus a result-name log.

Usage:
    uv run python agents/improve_deck.py "<scryfall query>" [--limit N] [--pages N] [--log FILE]

Runs the query (order=edhrec) and prints one line per card, at most --limit
(default 20): name | cost | type | P/T | oracle text (truncated; lines joined with
" / ", faces with " // ", an empty face shown as "(no text)"). Every result name,
not only the printed ones, is appended to --log, one per line, so the skill can
check that a sub-agent only returns cards that a search found. The result count
goes to stderr ("N results, M shown"). --pages is how many
result pages to read (175 cards each, default 1).
"""

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.card_view import _stats
from lib.card_model import Card, from_scryfall
from lib.scryfall import search_cards

DEFAULT_LIMIT = 20
MAX_TEXT = 200


def render_line(card: Card) -> str:
    texts = [" / ".join(line for line in f.oracle_text.splitlines() if line) for f in card.faces]
    text = " // ".join(t or "(no text)" for t in texts) if len(texts) > 1 else texts[0]
    if len(text) > MAX_TEXT:
        text = text[: MAX_TEXT - 3].rstrip() + "..."
    parts = [card.name, card.mana_cost, card.type_line, _stats(card.faces[0]), text]
    return " | ".join(p for p in parts if p)


def _parse(args: list[str]) -> tuple[str, int, int, str | None] | None:
    query, limit, pages, log = None, DEFAULT_LIMIT, 1, None
    it = iter(args)
    try:
        for arg in it:
            if arg == "--limit":
                limit = int(next(it))
            elif arg == "--pages":
                pages = int(next(it))
            elif arg == "--log":
                log = next(it)
            elif query is None and not arg.startswith("--"):
                query = arg
            else:
                return None
    except (StopIteration, ValueError):
        return None
    return (query, limit, pages, log) if query and limit >= 0 and pages >= 1 else None


def main(args: list[str], search=search_cards) -> int:
    parsed = _parse(args)
    if parsed is None:
        print(
            'Usage: improve_deck.py "<query>" [--limit N] [--pages N] [--log FILE]',
            file=sys.stderr,
        )
        return 1
    query, limit, pages, log = parsed

    try:
        results = search(query, pages=pages)
    except requests.HTTPError as e:
        try:
            details = e.response.json().get("details")
        except (AttributeError, ValueError):
            details = None
        status = getattr(e.response, "status_code", None)
        if status == 400:
            print(f"Scryfall rejected the query: {details or e}", file=sys.stderr)
        else:
            print(f"Scryfall error {status}: {details or e}", file=sys.stderr)
        return 1
    if log and results:
        with open(log, "a", encoding="utf-8") as f:
            f.writelines(c["name"] + "\n" for c in results)
    if not results:
        print("No results.")
    for raw in results[:limit]:
        print(render_line(from_scryfall(raw)))
    print(f"{len(results)} results, {min(limit, len(results))} shown", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
