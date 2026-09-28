"""Parse MTGO/Arena deck list text into structured data."""

import re
import sys

SIDEBOARD_MARKERS = {"sideboard", "side", "sb"}
# Plain header lines (Arena export style) → output section
SECTION_HEADERS = {
    "commander": "commander",
    "companion": "companion",
    "deck": "main",
    "sideboard": "side",
    "side": "side",
    "sb": "side",
}
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


def _is_sideboard_comment(line: str) -> bool:
    lower = line.lstrip("/ ").lower()
    return any(lower.startswith(m) for m in SIDEBOARD_MARKERS)


def _has_explicit_sections(lines: list[str]) -> bool:
    """True if any line is a section header, a sideboard comment or an SB: prefix."""
    for line in lines:
        if line.lower() in SECTION_HEADERS or line.upper().startswith("SB:"):
            return True
        if COMMENT_RE.match(line) and _is_sideboard_comment(line):
            return True
    return False


def parse(text: str) -> dict:
    sections = {"commander": [], "companion": [], "main": [], "side": []}
    lines = [raw.strip() for raw in text.splitlines()]
    # Without explicit markers, the first blank line after a card starts the sideboard.
    # With them, blank lines only group cards (e.g. creatures / spells / lands).
    blank_starts_side = not _has_explicit_sections(lines)
    current = "main"

    for line in lines:
        if not line:
            if current in ("commander", "companion"):
                current = "main"
            elif blank_starts_side and sections["main"]:
                current = "side"
            continue

        if COMMENT_RE.match(line):
            if _is_sideboard_comment(line):
                current = "side"
            continue

        if line.lower() in SECTION_HEADERS:
            current = SECTION_HEADERS[line.lower()]
            continue

        target = current
        # "SB: N CardName" Arena format
        if line.upper().startswith("SB:"):
            line = line[3:].strip()
            target = "side"

        m = CARD_LINE_RE.match(line)
        if not m:
            continue

        qty = int(m.group(1))
        name = _ARENA_SUFFIX_RE.sub("", m.group(2).strip())
        sections[target].append({"qty": qty, "name": name})

    return {**sections, "format": _extract_format(text)}


def unique_names(deck: dict) -> list[str]:
    names = set()
    for section in ("commander", "companion", "main", "side"):
        names |= {e["name"] for e in deck.get(section, [])}
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
    for section in ("commander", "companion"):
        if deck[section]:
            print(f"{section.title()}: {', '.join(e['name'] for e in deck[section])}")
    print(f"Format: {deck['format'] or 'unknown'}")
    print(json.dumps(deck, indent=2))
