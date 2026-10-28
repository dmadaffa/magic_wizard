"""Card fetcher script.

Usage:
    uv run python agents/card_fetcher.py [--refresh] "Cinder Dart" "Island" "Null Ripple"

Checks the local JSON Lines cache first; only calls Scryfall for cards not yet stored.
Cached cards older than 3 months (legality changes with rotations and bans) are
listed on stderr with their fetched_at date but not re-fetched. --refresh
re-fetches every named card; if that fails for a cached card, the old entry is
kept with a warning and it does not count as an error.
Prints a summary of hits and fetches. Exit code 0 on success, 1 if any card
could not be found. If Scryfall still answers 429 after a wait, the fetch stops and
the card that hit the limit plus every card not yet tried are listed as not fetched
(rate limit), separately from "Not found"; exit code 1.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Allow running as a script from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.cache import CardCache
from lib.scryfall import CardNotFoundError, RateLimitedError, fetch_card

STALE_AFTER = timedelta(days=90)  # "3 months"


def _is_stale(entry: dict) -> bool:
    try:
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
    except (KeyError, ValueError):
        return True
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - fetched_at > STALE_AFTER


def _fetched_date(entry: dict) -> str:
    return str(entry.get("fetched_at", "unknown"))[:10]


def main(names: list[str], cache: CardCache | None = None, refresh: bool = False) -> int:
    if not names:
        print("Usage: card_fetcher.py [--refresh] <card_name> [<card_name> ...]")
        return 1

    if cache is None:
        cache = CardCache()
    results = cache.get_many(names)

    cached = [n for n, v in results.items() if v is not None]
    misses = [n for n, v in results.items() if v is None]
    to_fetch = list(results) if refresh else misses
    hits = [n for n in cached if n not in to_fetch]

    errors = []
    fetched = []
    rate_limited = []

    kept_stale = []

    def keep_stale(name: str, reason: str) -> bool:
        """A failed re-fetch of a cached card keeps the old entry; not an error."""
        entry = results[name]
        if entry is None:
            return False
        print(
            f"WARNING: could not refresh {name!r} ({reason}); keeping the cached entry "
            f"from {_fetched_date(entry)}",
            file=sys.stderr,
        )
        kept_stale.append(name)
        return True

    for i, name in enumerate(to_fetch):
        try:
            data = fetch_card(name)
            cache.put(name, data)
            fetched.append(name)
        except CardNotFoundError:
            if not keep_stale(name, "not found"):
                errors.append(name)
        except RateLimitedError as exc:
            # Scryfall is already limiting us: stop, don't wait 30s per remaining card.
            print(f"  ERROR fetching {name!r}: {exc}", file=sys.stderr)
            for rest in to_fetch[i:]:
                if not keep_stale(rest, "Scryfall rate limit"):
                    rate_limited.append(rest)
            break
        except Exception as exc:  # noqa: BLE001 - one bad card must not abort the batch
            print(f"  ERROR fetching {name!r}: {exc}", file=sys.stderr)
            if not keep_stale(name, str(exc)):
                errors.append(name)

    stale = [n for n in cached if n not in to_fetch and _is_stale(results[n])]
    if stale:
        listed = ", ".join(f"{n} ({_fetched_date(results[n])})" for n in stale)
        print(
            f"WARNING: {len(stale)} cached card(s) are older than 3 months, so their "
            f"legality may have changed: {listed}. Re-run with --refresh to re-fetch.",
            file=sys.stderr,
        )

    print(f"Cache hits : {len(hits)}")
    print(f"Fetched    : {len(fetched)}")
    if refresh:
        print(f"Kept stale : {len(kept_stale)}")
    if errors:
        print(f"Not found  : {len(errors)}")
        for e in errors:
            print(f"  - {e}")

    if rate_limited:
        print(
            f"Not fetched (Scryfall rate limit), try again later: {len(rate_limited)}"
        )
        for r in rate_limited:
            print(f"  - {r}")

    return 1 if errors or rate_limited else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--refresh"]
    sys.exit(main(args, refresh="--refresh" in sys.argv[1:]))
