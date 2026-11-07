"""Card fetcher script.

Usage:
    uv run python agents/card_fetcher.py [--refresh] "Cinder Dart" "Island" "Null Ripple"

Checks the local JSON Lines cache first; only calls Scryfall for cards not yet stored.
Those are fetched in batches of 75 (/cards/collection), each batch written to the cache
at once; names the batch does not return are retried one by one (/cards/named).
Names that differ only in whitespace are requested once.
Cached cards older than 3 months (legality changes with rotations and bans) are
listed on stderr with their fetched_at date but not re-fetched. --refresh
re-fetches every named card; if that fails for a cached card, the old entry is
kept with a warning and it does not count as an error.
Prints a summary of hits and fetches. Exit code 0 on success, 1 if any card
could not be found. If Scryfall still answers 429 after a wait, the fetch stops and
every card not yet fetched is listed as not fetched
(rate limit), separately from "Not found"; exit code 1.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Allow running as a script from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.cache import CardCache, normalize_name
from lib.scryfall import (
    COLLECTION_BATCH_SIZE,
    CardNotFoundError,
    RateLimitedError,
    fetch_card,
    fetch_cards,
)

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

    # One request per normalized name; the outcome applies to every caller name in the group.
    groups: dict[str, list[str]] = {}
    for name in to_fetch:
        groups.setdefault(normalize_name(name), []).append(name)
    reps = list(groups)  # the normalized names are what Scryfall is asked for

    def members(rep: str) -> list[str]:
        return groups[rep]

    def fail(rep: str, reason: str) -> None:
        """A failed fetch or store: keep the old entry if there is one, else it is an error."""
        for name in members(rep):
            if not keep_stale(name, reason):
                errors.append(name)

    unmatched: list[str] = []  # reps the batch request did not return: retried one by one
    limited: list[str] = []  # reps not fetched because Scryfall rate-limited us

    for start in range(0, len(reps), COLLECTION_BATCH_SIZE):
        batch = reps[start:start + COLLECTION_BATCH_SIZE]
        try:
            found = fetch_cards(batch)
        except RateLimitedError as exc:
            print(f"  ERROR fetching a batch of {len(batch)} cards: {exc}", file=sys.stderr)
            limited = unmatched + reps[start:]
            unmatched = []
            break
        except Exception as exc:  # noqa: BLE001 - fall back to one request per card
            print(f"  ERROR fetching a batch of {len(batch)} cards: {exc}", file=sys.stderr)
            found = {}
        if found:
            try:
                cache.put_many(found)
            except Exception as exc:  # noqa: BLE001 - e.g. the cache file is locked
                print(f"  ERROR storing a batch of {len(found)} cards: {exc}", file=sys.stderr)
                for rep in found:
                    fail(rep, str(exc))
            else:
                for rep in found:
                    fetched.extend(members(rep))
        unmatched.extend(rep for rep in batch if rep not in found)

    for i, rep in enumerate(unmatched):
        try:
            cache.put(rep, fetch_card(rep))
            fetched.extend(members(rep))
        except CardNotFoundError:
            fail(rep, "not found")
        except RateLimitedError as exc:
            # Scryfall is already limiting us: stop, don't wait 30s per remaining card.
            print(f"  ERROR fetching {rep!r}: {exc}", file=sys.stderr)
            limited = unmatched[i:]
            break
        except Exception as exc:  # noqa: BLE001 - one bad card must not abort the batch
            print(f"  ERROR fetching {rep!r}: {exc}", file=sys.stderr)
            fail(rep, str(exc))

    for rep in limited:
        for name in members(rep):
            if not keep_stale(name, "Scryfall rate limit"):
                rate_limited.append(name)

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
