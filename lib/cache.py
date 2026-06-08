"""CSV-backed card cache with a swappable interface.

To upgrade to SQLite: create lib/cache_sql.py implementing the same
CardCache interface, then change the import in agents/card_fetcher.py.
"""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

CACHE_PATH = Path(__file__).parent.parent / "data" / "card_cache.csv"

COLUMNS = [
    "name", "mana_cost", "cmc", "type_line",
    "colors", "color_identity", "oracle_text",
    "power", "toughness", "loyalty",
    "legal_standard", "legal_modern", "legal_pioneer",
    "legal_legacy", "legal_commander",
    "fetched_at",
]


class CardCache:
    def __init__(self, path: Path = CACHE_PATH):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            with open(self._path, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=COLUMNS).writeheader()

    def _load(self) -> dict[str, dict]:
        with open(self._path, newline="", encoding="utf-8") as f:
            return {row["name"]: row for row in csv.DictReader(f)}

    def get(self, name: str) -> dict | None:
        return self._load().get(name)

    def get_many(self, names: list[str]) -> dict[str, dict | None]:
        store = self._load()
        return {name: store.get(name) for name in names}

    def put(self, name: str, data: dict) -> None:
        store = self._load()
        entry = {col: data.get(col, "") for col in COLUMNS}
        entry["name"] = name
        entry["fetched_at"] = datetime.now(timezone.utc).isoformat()
        store[name] = entry
        with open(self._path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(store.values())
