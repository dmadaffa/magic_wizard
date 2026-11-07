"""JSON Lines card cache with a swappable interface.

Each line is {"name": <normalized deck name>, "fetched_at": <iso time>,
"scryfall": <trimmed card object>}.
Interpret entries with lib.card_model.from_scryfall(entry["scryfall"]).

To upgrade to SQLite: create lib/cache_sql.py implementing the same
CardCache interface, keying every entry by normalize_name (defined here),
then change the import in agents/card_fetcher.py, agents/card_view.py
and agents/deck_stats.py.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

CACHE_PATH = Path(__file__).parent.parent / "data" / "card_cache.jsonl"


def normalize_name(name: str) -> str:
    """Cache key for a card name: trim the ends and collapse inner whitespace runs
    (so a stray "\\r" from CRLF input never becomes part of the key). Case is kept."""
    return " ".join(name.split())


class CardCache:
    def __init__(self, path: Path = CACHE_PATH):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch()

    def _load(self) -> dict[str, dict]:
        """Keys are normalized. Lines that collapse to one name keep the newest
        fetched_at (the later line on a tie); the stored name is the normalized one."""
        store: dict[str, dict] = {}
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                key = normalize_name(entry["name"])
                known = store.get(key)
                if known is None or entry.get("fetched_at", "") >= known.get("fetched_at", ""):
                    store[key] = {**entry, "name": key}
        return store

    def get(self, name: str) -> dict | None:
        return self._load().get(normalize_name(name))

    def get_many(self, names: list[str]) -> dict[str, dict | None]:
        store = self._load()
        return {name: store.get(normalize_name(name)) for name in names}

    def put(self, name: str, card: dict) -> None:
        name = normalize_name(name)
        store = self._load()
        store[name] = {
            "name": name,
            "fetched_at": datetime.now(UTC).isoformat(),
            "scryfall": card,
        }
        # Write a temp file next to the cache, then swap it in, so a failed
        # write never leaves the cache truncated. fsync the temp file first so a
        # crash right after the rename can't leave it empty.
        tmp_path = self._path.with_name(self._path.name + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(json.dumps(entry, ensure_ascii=False) + "\n" for entry in store.values())
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
