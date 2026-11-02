"""Standard rotation: turns data/standard_rotation.json into Scryfall search filters.

No network here. `today` is passed in so tests control the clock.
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROTATION_PATH = Path(__file__).parent.parent / "data" / "standard_rotation.json"
# Rotation counts as active when it is at most this many days (~6 months) away.
ROTATION_WARNING_DAYS = 183
# Encoded URL budget for one search request (leaves headroom under Scryfall's limit).
MAX_QUERY_URL_CHARS = 1800
_SURVIVING_TYPES = ("expansion", "core")


@dataclass
class Rotation:
    next_rotation: date
    rotating: list[str]
    evergreen: list[str]


def load_rotation(path: Path = ROTATION_PATH) -> Rotation:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Rotation(
        next_rotation=date.fromisoformat(data["next_rotation"]),
        rotating=list(data["rotating"]),
        evergreen=list(data["evergreen"]),
    )


def surviving_sets(sets: list[dict], rotation: Rotation) -> list[str]:
    """Codes of the paper expansion/core sets that stay in Standard, plus evergreen sets.

    Cutoff: sets released on or after the oldest rotating set's release date. Returns []
    when none of the rotating codes is in `sets` (the caller should warn and treat
    rotation as inactive).
    """
    dates = [s["released_at"] for s in sets if s["code"] in rotation.rotating]
    if not dates:
        return []
    cutoff = min(dates)
    codes = [
        s["code"] for s in sets
        if not s.get("digital") and s.get("set_type") in _SURVIVING_TYPES
        and s["code"] not in rotation.rotating and s["released_at"] >= cutoff
    ]
    codes += [c for c in rotation.evergreen if c not in codes]
    return codes


def days_left(rotation: Rotation, today: date) -> int:
    return (rotation.next_rotation - today).days


def status(rotation: Rotation, today: date) -> str:
    """'active' (rotation within the warning window), 'inactive' (further away) or 'stale' (date passed)."""
    d = days_left(rotation, today)
    if d <= 0:
        return "stale"
    return "active" if d <= ROTATION_WARNING_DAYS else "inactive"


def survival_prefix(surviving: list[str]) -> str:
    """Filter for cards with a printing in a surviving set."""
    return "(" + " or ".join(f"in:{c}" for c in surviving) + ")"


def rotating_query(surviving: list[str], names: list[str]) -> list[str]:
    """Queries for the named cards that rotate; split so each encoded URL stays under the limit."""
    base = "f:standard " + " ".join(f"-in:{c}" for c in surviving)

    def build(terms: list[str]) -> str:
        return f"{base} ({' or '.join(terms)})"

    queries: list[str] = []
    terms: list[str] = []
    for name in names:
        term = '!"' + name.replace('"', '\\"') + '"'
        if terms and len(quote(build(terms + [term]))) > MAX_QUERY_URL_CHARS:
            queries.append(build(terms))
            terms = []
        terms.append(term)
    if terms:
        queries.append(build(terms))
    return queries


def color_filter(colors: list[str]) -> str:
    return "id<=" + ("".join(c.lower() for c in colors) or "c")
