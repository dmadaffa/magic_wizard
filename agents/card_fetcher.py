"""Card fetcher sub-agent.

Usage:
    uv run python agents/card_fetcher.py "Cinder Dart" "Island" "Null Ripple"

Checks the local CSV cache first; only calls Scryfall for cards not yet stored.
Prints a summary of hits and fetches. Exit code 0 on success, 1 if any card
could not be found.
"""

import sys
from pathlib import Path

# Allow running as a script from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.cache import CardCache
from lib.scryfall import CardNotFoundError, fetch_card


def main(names: list[str], cache: CardCache | None = None) -> int:
    if not names:
        print("Usage: card_fetcher.py <card_name> [<card_name> ...]")
        return 1

    if cache is None:
        cache = CardCache()
    results = cache.get_many(names)

    hits = [n for n, v in results.items() if v is not None]
    misses = [n for n, v in results.items() if v is None]

    errors = []
    fetched = []

    for name in misses:
        try:
            data = fetch_card(name)
            cache.put(name, data)
            fetched.append(name)
        except CardNotFoundError:
            errors.append(name)
        except Exception as exc:  # noqa: BLE001 - one bad card must not abort the batch
            print(f"  ERROR fetching {name!r}: {exc}", file=sys.stderr)
            errors.append(name)

    print(f"Cache hits : {len(hits)}")
    print(f"Fetched    : {len(fetched)}")
    if errors:
        print(f"Not found  : {len(errors)}")
        for e in errors:
            print(f"  - {e}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
