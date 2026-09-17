"""Thin Scryfall API client — returns card objects trimmed of images, prices and links."""

import time
import requests

BASE_URL = "https://api.scryfall.com"
# /cards/named is capped at 2/second; 550ms gives headroom without being wasteful
_RATE_LIMIT_SLEEP = 0.55
_HEADERS = {"User-Agent": "magic-wizard-deck-assistant/0.1 (personal project)"}

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

_MAX_RETRIES = 5
_BACKOFF_BASE = 2.0  # seconds; doubles each retry: 2, 4, 8, 16, 32


class CardNotFoundError(Exception):
    pass


def _get_with_backoff(url: str, **kwargs) -> requests.Response:
    """GET with exponential backoff on 429 responses."""
    for attempt in range(_MAX_RETRIES):
        time.sleep(_RATE_LIMIT_SLEEP)
        resp = requests.get(url, **kwargs)
        if resp.status_code != 429:
            return resp
        wait = _BACKOFF_BASE ** attempt
        print(f"[scryfall] 429 rate-limited — retrying in {wait:.0f}s (attempt {attempt + 1}/{_MAX_RETRIES})")
        time.sleep(wait)
    # Final attempt after max retries
    time.sleep(_RATE_LIMIT_SLEEP)
    return requests.get(url, **kwargs)


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
