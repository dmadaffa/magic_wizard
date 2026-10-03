"""JSON Lines card cache with a swappable interface.

Each line is {"name": <deck name>, "fetched_at": <iso time>, "scryfall": <trimmed card object>}.
Interpret entries with lib.card_model.from_scryfall(entry["scryfall"]).

To upgrade to SQLite: create lib/cache_sql.py implementing the same
CardCache interface, then change the import in agents/card_fetcher.py and agents/card_view.py.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

CACHE_PATH = Path(__file__).parent.parent / "data" / "card_cache.jsonl"


class CardCache:
    def __init__(self, path: Path = CACHE_PATH):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch()

    def _load(self) -> dict[str, dict]:
        with open(self._path, encoding="utf-8") as f:
            entries = (json.loads(line) for line in f if line.strip())
            return {entry["name"]: entry for entry in entries}

    def get(self, name: str) -> dict | None:
        return self._load().get(name)

    def get_many(self, names: list[str]) -> dict[str, dict | None]:
        store = self._load()
        return {name: store.get(name) for name in names}

    def put(self, name: str, card: dict) -> None:
        store = self._load()
        store[name] = {
            "name": name,
            "fetched_at": datetime.now(UTC).isoformat(),
            "scryfall": card,
        }
        # Write a temp file next to the cache, then swap it in, so a failed
        # write never leaves the cache truncated.
        tmp_path = self._path.with_name(self._path.name + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(json.dumps(entry, ensure_ascii=False) + "\n" for entry in store.values())
            os.replace(tmp_path, self._path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
