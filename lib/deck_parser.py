"""Parse MTGO/Arena deck list text into structured data."""

import re
import sys

SIDEBOARD_MARKERS = {"sideboard", "side", "sb"}
KNOWN_FORMATS = {"standard", "pioneer", "modern", "legacy", "vintage", "commander", "pauper", "historic", "explorer", "alchemy"}
COMMENT_RE = re.compile(r"^//")
CARD_LINE_RE = re.compile(r"^(\d+)x?\s+(.+)$")
# Strips Arena/MTGO set-code suffix: "Card Name (SET) 123" → "Card Name"
_ARENA_SUFFIX_RE = re.compile(r"\s+\([A-Z0-9]+\)\s+\d+$")


def _extract_format(text: str) -> str | None:
    """Return the first known format name found in leading comment lines, or None."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not COMMENT_RE.match(line):
            break
        lower = line.lower()
        for fmt in KNOWN_FORMATS:
            if fmt in lower:
                return fmt.title()
    return None


def parse(text: str) -> dict:
    main = []
    side = []
    in_sideboard = False
    blank_seen = False

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            # A blank line after at least one main-deck card = sideboard starts
            if main:
                blank_seen = True
            continue

        if COMMENT_RE.match(line):
            # Check if comment signals sideboard
            lower = line.lstrip("/ ").lower()
            if any(lower.startswith(m) for m in SIDEBOARD_MARKERS):
                in_sideboard = True
            continue

        # Plain section header (e.g. "Deck", "Sideboard") — no leading digit
        if line.lower() in SIDEBOARD_MARKERS:
            in_sideboard = True
            continue

        # "SB: N CardName" Arena format
        if line.upper().startswith("SB:"):
            line = line[3:].strip()
            in_sideboard = True

        m = CARD_LINE_RE.match(line)
        if not m:
            continue

        qty = int(m.group(1))
        name = _ARENA_SUFFIX_RE.sub("", m.group(2).strip())
        entry = {"qty": qty, "name": name}

        if in_sideboard or blank_seen:
            side.append(entry)
        else:
            main.append(entry)

    return {"main": main, "side": side, "format": _extract_format(text)}


def unique_names(deck: dict) -> list[str]:
    names = {e["name"] for e in deck["main"]}
    names |= {e["name"] for e in deck["side"]}
    return sorted(names)


if __name__ == "__main__":
    import json
    path = sys.argv[1] if len(sys.argv) > 1 else "decks/example_deck.txt"
    # Optional second arg overrides the format detected from the file header
    format_override = sys.argv[2] if len(sys.argv) > 2 else None
    with open(path, encoding="utf-8") as f:
        deck = parse(f.read())
    if format_override:
        deck["format"] = format_override.title()
    main_count = sum(e["qty"] for e in deck["main"])
    side_count = sum(e["qty"] for e in deck["side"])
    print(f"Main deck: {main_count} cards ({len(deck['main'])} unique)")
    print(f"Sideboard: {side_count} cards ({len(deck['side'])} unique)")
    print(f"Format: {deck['format'] or 'unknown'}")
    print(json.dumps(deck, indent=2))
