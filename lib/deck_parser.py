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
_FORMAT_RE = re.compile(r"(?<![\w-])(" + "|".join(sorted(KNOWN_FORMATS)) + r")(?!\w)", re.IGNORECASE)
COMMENT_RE = re.compile(r"^//")
CARD_LINE_RE = re.compile(r"^(\d+)x?\s+(.+)$")
# Strips Arena/MTGO set-code suffix: "Card Name (SET) 123" → "Card Name".
# Collector numbers: 123, 276p, 12★, 12†, S1 / A12 (letter prefix), or SET-123 style
# (ABC-123), optionally followed by a Moxfield foil marker (*F*, *E*).
# The "(SET)" group is required, so name tails like "Name S1" are kept.
_ARENA_SUFFIX_RE = re.compile(
    r"\s+\([A-Z0-9]+\)\s+(?:[A-Z0-9]+-)?[A-Za-z]*\d+[A-Za-z★†]*(?:\s+\*[A-Z]\*)?$"
)


def _extract_format(text: str) -> str | None:
    """Return the known format named in the header lines, or None.

    The header is every line before the first card line (comments and plain
    lines like "Standard Deck"). Matching is case-insensitive and whole-word; a leading hyphen joins
    words ("Pre-Modern" is not Modern), a trailing one doesn't ("Pauper-legal").
    The first header line naming a format wins; within it, the format that
    appears first in the line wins. A bare section header (`Commander`, `Deck`,
    ...) is skipped: it names a section, not a format. A line that merely
    contains one, like "Deck standard", still counts.
    """
    for raw in text.splitlines():
        line = raw.strip()
        if CARD_LINE_RE.match(line) or line.upper().startswith("SB:"):
            break
        if line.lower() in SECTION_HEADERS:
            continue
        m = _FORMAT_RE.search(line)
        if m:
            return m.group(1).title()
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
    # Usage: deck_parser.py [path] [format words...]
    # stdout: the deck as JSON only. stderr: human-readable summary.
    import json
    path = sys.argv[1] if len(sys.argv) > 1 else "decks/example_deck.txt"
    # Optional remaining args override the format detected from the file header
    # (joined, so an unquoted multi-word format still works)
    format_override = " ".join(sys.argv[2:]) or None
    with open(path, encoding="utf-8") as f:
        deck = parse(f.read())
    if format_override:
        deck["format"] = format_override.title()
    main_count = sum(e["qty"] for e in deck["main"])
    side_count = sum(e["qty"] for e in deck["side"])
    # Summary goes to stderr so stdout is exactly the JSON document.
    print(f"Main deck: {main_count} cards ({len(deck['main'])} unique)", file=sys.stderr)
    print(f"Sideboard: {side_count} cards ({len(deck['side'])} unique)", file=sys.stderr)
    for section in ("commander", "companion"):
        if deck[section]:
            print(f"{section.title()}: {', '.join(e['name'] for e in deck[section])}", file=sys.stderr)
    print(f"Format: {deck['format'] or 'unknown'}", file=sys.stderr)
    print(json.dumps(deck, indent=2))
