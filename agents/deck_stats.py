"""Deck stats script: mana curve, color counts and mana sources for the main deck.

Usage:
    uv run python agents/deck_stats.py <deck file>

Parses the deck, loads its main-deck cards from the cache and prints compact
text on stdout (see lib/stats.py for the rules). Cards missing from the cache
are reported as `NOT CACHED: <name>` on stderr and the exit code is 1; stats
for the rest are still printed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.cache import CardCache
from lib.card_model import from_scryfall
from lib.deck_parser import parse
from lib.stats import deck_stats, render


def main(argv: list[str], cache: CardCache | None = None) -> int:
    if len(argv) != 1:
        print("Usage: deck_stats.py <deck file>", file=sys.stderr)
        return 1

    deck = parse(Path(argv[0]).read_text(encoding="utf-8"))
    if cache is None:
        cache = CardCache()

    copies: dict[str, int] = {}
    for entry in deck["main"]:
        copies[entry["name"]] = copies.get(entry["name"], 0) + entry["qty"]

    entries, missing = [], []
    for name, cached in cache.get_many(list(copies)).items():
        if cached is None:
            missing.append(name)
            continue
        card = from_scryfall(cached["scryfall"])
        for warning in card.warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
        entries.append((card, copies[name]))

    print(render(deck_stats(entries)))
    for name in missing:
        print(f"NOT CACHED: {name}", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
