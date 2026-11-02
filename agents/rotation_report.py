"""Standard rotation report for a deck list.

Usage:
    uv run python agents/rotation_report.py <deck file>
    uv run python agents/rotation_report.py --prefix

Prints the deck's cards that rotate out of Standard at the next rotation, or why
there is nothing to report: rotation more than 6 months away,
data/standard_rotation.json out of date, or its rotating set codes not found in
Scryfall's sets (the last two also warn on stderr). With
--prefix only the survival search prefix is printed (empty when rotation is not
active), for /improve-deck to put in front of its searches.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import rotation as rot
from lib.deck_parser import parse, unique_names
from lib.scryfall import SETS_PATH, load_sets, search_cards

_BASICS = {"plains", "island", "swamp", "mountain", "forest", "wastes"}


def _is_basic(name: str) -> bool:
    return name.lower().removeprefix("snow-covered ") in _BASICS


def main(
    args: list[str],
    today: date | None = None,
    rotation_path: Path = rot.ROTATION_PATH,
    sets_path: Path = SETS_PATH,
    search=search_cards,
) -> int:
    today = today or date.today()
    rotation = rot.load_rotation(rotation_path)
    state = rot.status(rotation, today)
    if state == "stale":
        print(
            f"WARNING: the rotation date {rotation.next_rotation} has passed; add the next "
            "rotation to data/standard_rotation.json when it is announced.",
            file=sys.stderr,
        )

    surviving: list[str] = []
    if state == "active":
        surviving = rot.surviving_sets(load_sets(sets_path), rotation)
        if not surviving:
            print(
                "WARNING: no rotating set from data/standard_rotation.json was found in "
                "Scryfall's sets; check the set codes. Treating rotation as inactive.",
                file=sys.stderr,
            )
            state = "skipped"

    if args == ["--prefix"]:
        print(rot.survival_prefix(surviving) if state == "active" else "")
        return 0
    if len(args) != 1:
        print("Usage: rotation_report.py <deck file> | --prefix", file=sys.stderr)
        return 1

    if state == "stale":
        print(f"Rotation data is out of date (rotation date {rotation.next_rotation} has passed).")
        return 0
    if state == "skipped":
        print(
            "Rotation report skipped: the rotating set codes in data/standard_rotation.json "
            "were not found in Scryfall's sets."
        )
        return 0
    if state == "inactive":
        print(f"The next rotation ({rotation.next_rotation}) is more than 6 months away.")
        return 0

    deck = parse(Path(args[0]).read_text(encoding="utf-8"))
    names = [n for n in unique_names(deck) if not _is_basic(n)]
    found: set[str] = set()
    for query in rot.rotating_query(surviving, names):
        found.update(c["name"] for c in search(query, pages=1))
    print(f"Rotation on {rotation.next_rotation}, {rot.days_left(rotation, today)} days left.")
    if not found:
        print("No cards in this deck rotate.")
    for name in sorted(found):
        print(f"ROTATING: {name}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
