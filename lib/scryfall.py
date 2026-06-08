"""Thin Scryfall API client — returns only the fields we need."""

import time
import requests

BASE_URL = "https://api.scryfall.com"
_RATE_LIMIT_SLEEP = 0.05  # 50ms between requests per Scryfall guidelines
_HEADERS = {"User-Agent": "magic-wizard-deck-assistant/0.1 (personal project)"}

FIELDS = (
    "name", "mana_cost", "cmc", "type_line",
    "colors", "color_identity", "oracle_text",
    "power", "toughness", "loyalty",
)
LEGALITY_FORMATS = ("standard", "modern", "pioneer", "legacy", "commander")


class CardNotFoundError(Exception):
    pass


def fetch_card(name: str) -> dict:
    """Fetch a single card by exact name. Raises CardNotFoundError if not found."""
    time.sleep(_RATE_LIMIT_SLEEP)
    resp = requests.get(
        f"{BASE_URL}/cards/named",
        params={"exact": name},
        headers=_HEADERS,
        timeout=10,
    )

    if resp.status_code == 404:
        raise CardNotFoundError(f"Card not found: {name!r}")
    resp.raise_for_status()

    data = resp.json()

    # Handle double-faced cards — use front face fields where missing on root
    face = data
    if "card_faces" in data and "oracle_text" not in data:
        face = data["card_faces"][0]

    result = {field: face.get(field, "") for field in FIELDS}

    # Normalize list fields to pipe-separated strings for CSV friendliness
    for list_field in ("colors", "color_identity"):
        val = result[list_field]
        result[list_field] = "|".join(val) if isinstance(val, list) else (val or "")

    # flatten legality booleans
    legalities = data.get("legalities", {})
    for fmt in LEGALITY_FORMATS:
        result[f"legal_{fmt}"] = legalities.get(fmt, "not_legal")

    return result
