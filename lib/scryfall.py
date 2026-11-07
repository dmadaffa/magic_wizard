"""Thin Scryfall API client — returns card objects trimmed of images, prices and links.

Cards are fetched in batches with fetch_cards (/cards/collection) or one by one with
fetch_card (/cards/named); every request is spaced out and backs off on a 429.
"""

import json
import sys
import time
import tomllib
from pathlib import Path

import requests

BASE_URL = "https://api.scryfall.com"
# /cards/named is capped at 2/second; 550ms gives headroom without being wasteful
_RATE_LIMIT_SLEEP = 0.55
_ROOT = Path(__file__).parent.parent
with open(_ROOT / "pyproject.toml", "rb") as _f:
    _VERSION = tomllib.load(_f)["project"]["version"]
# Scryfall asks for an accurate User-Agent (app name and version) and an Accept header.
_HEADERS = {
    "User-Agent": f"magic-wizard/{_VERSION} (+https://github.com/dmadaffa/magic_wizard)",
    "Accept": "application/json",
}

# Default legality columns, shown when no format is given; the full legalities dict is still stored.
LEGALITY_FORMATS = ("standard", "modern", "pioneer", "legacy", "commander")

# Keys dropped before caching: images, prices, links and print trivia. Everything
# else is kept, so new Scryfall fields (and new mechanics) need no re-fetch.
_DROP_KEYS = frozenset({
    "image_uris", "image_status", "image_updated_at", "highres_image",
    "prices", "purchase_uris", "related_uris", "uri", "scryfall_uri",
    "rulings_uri", "prints_search_uri", "set_uri", "set_search_uri",
    "scryfall_set_uri", "multiverse_ids", "mtgo_id", "mtgo_foil_id",
    "arena_id", "tcgplayer_id", "tcgplayer_etched_id", "cardmarket_id",
    "resource_id", "artist", "artist_id", "artist_ids", "illustration_id",
    "card_back_id", "flavor_text", "border_color", "frame", "frame_effects",
    "security_stamp", "full_art", "textless", "booster", "story_spotlight",
    "promo_types", "finishes", "foil", "nonfoil", "oversized", "promo",
    "variation", "preview",
})

# /cards/collection accepts at most 75 identifiers per request.
COLLECTION_BATCH_SIZE = 75

# Scryfall limits access for 30s after a 429; waiting less just draws another one.
_RATE_LIMIT_WAIT = 30.0


class CardNotFoundError(Exception):
    pass


class RateLimitedError(Exception):
    """Scryfall answered 429 again after the 30s wait; stop sending requests."""


def _retry_after(resp: requests.Response) -> float:
    try:
        return float(resp.headers.get("Retry-After", 0))
    except (TypeError, ValueError):
        return 0.0


def _send_with_backoff(send, url: str, **kwargs) -> requests.Response:
    """Send with `send` (requests.get or requests.post), spaced out; on a 429 tell the
    user, wait max(30s, Retry-After), retry once.

    A second 429 raises RateLimitedError: Scryfall bans clients that keep going.
    """
    time.sleep(_RATE_LIMIT_SLEEP)
    resp = send(url, **kwargs)
    if resp.status_code != 429:
        return resp
    wait = max(_RATE_LIMIT_WAIT, _retry_after(resp))
    print(
        f"[scryfall] This run is taking longer than usual because of Scryfall's "
        f"rate limit (HTTP 429). Waiting {wait:.0f}s before retrying once.",
        file=sys.stderr,
    )
    time.sleep(wait)
    time.sleep(_RATE_LIMIT_SLEEP)
    resp = send(url, **kwargs)
    if resp.status_code == 429:
        raise RateLimitedError(
            "Scryfall is still rate-limiting requests (HTTP 429) after a "
            f"{wait:.0f}s wait; try again later"
        )
    return resp


def _get_with_backoff(url: str, **kwargs) -> requests.Response:
    return _send_with_backoff(requests.get, url, **kwargs)


def _post_with_backoff(url: str, **kwargs) -> requests.Response:
    return _send_with_backoff(requests.post, url, **kwargs)


def fetch_card(name: str) -> dict:
    """Fetch a card by exact name as a trimmed Scryfall object. Raises CardNotFoundError if not found."""
    resp = _get_with_backoff(
        f"{BASE_URL}/cards/named",
        params={"exact": name},
        headers=_HEADERS,
        timeout=10,
    )

    if resp.status_code == 404:
        raise CardNotFoundError(f"Card not found: {name!r}")
    resp.raise_for_status()

    return trim_card(resp.json())


def fetch_cards(names: list[str]) -> dict[str, dict]:
    """Fetch up to COLLECTION_BATCH_SIZE cards by name in one /cards/collection request.

    Returns requested name -> trimmed card. A card matches a name if the name equals,
    case-insensitively, its `name` or one of its face names (order of `data` and
    `not_found` are not used). Names with no match are left out: the caller decides
    what to do with them. Raises RateLimitedError after a second 429.
    """
    resp = _post_with_backoff(
        f"{BASE_URL}/cards/collection",
        json={"identifiers": [{"name": n} for n in names]},
        headers=_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    by_name: dict[str, dict] = {}
    cards = resp.json()["data"]
    for card in cards:
        by_name.setdefault(card["name"].casefold(), card)
    for card in cards:  # a face name only counts where no card has that full name
        for face in card.get("card_faces", []):
            by_name.setdefault(face["name"].casefold(), card)
    return {n: trim_card(by_name[n.casefold()]) for n in names if n.casefold() in by_name}


def fetch_card_names() -> list[str]:
    """Every card name Scryfall knows (one /catalog/card-names request)."""
    resp = _get_with_backoff(f"{BASE_URL}/catalog/card-names", headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()["data"]


def _trim(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if k not in _DROP_KEYS}


def trim_card(data: dict) -> dict:
    """Strip presentation-only keys from a Scryfall card object, keeping faces and related parts."""
    card = _trim(data)
    if "card_faces" in card:
        card["card_faces"] = [_trim(face) for face in card["card_faces"]]
    if "all_parts" in card:
        card["all_parts"] = [_trim(part) for part in card["all_parts"]]
    return card


def search_cards(query: str, order: str = "edhrec", pages: int = 1) -> list[dict]:
    """Trimmed card objects matching a Scryfall search; follows next_page up to `pages` pages.

    A 404 (no match) gives []. Requests are sequential and go through the backoff.
    """
    cards: list[dict] = []
    url = f"{BASE_URL}/cards/search"
    params: dict | None = {"q": query, "order": order}
    for _ in range(pages):
        resp = _get_with_backoff(url, params=params, headers=_HEADERS, timeout=30)
        if resp.status_code == 404:
            return cards
        resp.raise_for_status()
        body = resp.json()
        cards.extend(trim_card(c) for c in body["data"])
        if not body.get("has_more") or not body.get("next_page"):
            break
        url, params = body["next_page"], None
    return cards


def fetch_sets() -> list[dict]:
    """Every Scryfall set (one /sets request)."""
    resp = _get_with_backoff(f"{BASE_URL}/sets", headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()["data"]


SETS_PATH = _ROOT / "data" / "scryfall_sets.json"
_SETS_MAX_AGE = 24 * 3600


def load_sets(path: Path = SETS_PATH, fetch=None) -> list[dict]:
    """Scryfall sets cached in `path`; downloaded when missing or older than 1 day."""
    if not path.exists() or time.time() - path.stat().st_mtime > _SETS_MAX_AGE:
        try:
            sets = (fetch or fetch_sets)()
        except Exception as e:  # noqa: BLE001 - offline, Scryfall down, ...
            if not path.exists():
                raise
            print(f"[scryfall] could not refresh sets ({e}); using the cached file", file=sys.stderr)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(sets, ensure_ascii=False), encoding="utf-8")
            return sets
    return json.loads(path.read_text(encoding="utf-8"))
