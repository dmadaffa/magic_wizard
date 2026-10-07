"""Thin Scryfall API client — returns card objects trimmed of images, prices and links."""

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

# Legality columns shown by the analysis; the full legalities dict is still stored.
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


def _get_with_backoff(url: str, **kwargs) -> requests.Response:
    """GET; on a 429 tell the user, wait max(30s, Retry-After), retry once.

    A second 429 raises RateLimitedError: Scryfall bans clients that keep going.
    """
    time.sleep(_RATE_LIMIT_SLEEP)
    resp = requests.get(url, **kwargs)
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
    resp = requests.get(url, **kwargs)
    if resp.status_code == 429:
        raise RateLimitedError(
            "Scryfall is still rate-limiting requests (HTTP 429) after a "
            f"{wait:.0f}s wait; try again later"
        )
    return resp


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
