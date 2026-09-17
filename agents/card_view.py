"""Card view sub-agent: prints compact card lines from the cache for the analysis step.

Usage:
    uv run python agents/card_view.py "Card Name 1" "Card Name 2"

Multi-face cards print one indented line per face, tagged with how that face
is reached (cast, transform, prepared, ...). Exit code 1 if any card is not
cached; warnings (e.g. unknown layouts) go to stderr.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.cache import CardCache
from lib.card_model import Card, Face, from_scryfall
from lib.scryfall import LEGALITY_FORMATS


def _fmt_number(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


def _stats(face: Face) -> str:
    if face.power or face.toughness:
        return f"{face.power}/{face.toughness}"
    if face.loyalty:
        return f"loyalty {face.loyalty}"
    if face.defense:
        return f"defense {face.defense}"
    return ""


def _text_lines(text: str, indent: str) -> list[str]:
    return [indent + line for line in text.splitlines() if line]


def render(card: Card) -> str:
    legality = ", ".join(f"{fmt}:{card.legalities.get(fmt, 'not_legal')}" for fmt in LEGALITY_FORMATS)
    identity = "".join(card.color_identity) or "C"
    header = [card.name]
    if len(card.faces) > 1:
        header.append(card.layout)
    else:
        header.append(card.mana_cost)
    header += [f"CMC {_fmt_number(card.cmc)}", f"identity {identity}"]
    if len(card.faces) == 1:
        header.append(card.type_line)
        if stats := _stats(card.faces[0]):
            header.append(stats)
    header.append(legality)
    lines = [" | ".join(part for part in header if part)]

    is_basic = card.type_line.startswith("Basic Land")
    if len(card.faces) == 1:
        if not is_basic:
            lines += _text_lines(card.faces[0].oracle_text, "    ")
        return "\n".join(lines)

    for i, face in enumerate(card.faces, start=1):
        access = ", ".join(sorted(face.access))
        parts = [f"  [face {i}: {access}] {face.name}", face.mana_cost, face.type_line, _stats(face)]
        lines.append(" | ".join(part for part in parts if part))
        lines += _text_lines(face.oracle_text, "    ")
    return "\n".join(lines)


def main(names: list[str], cache: CardCache | None = None) -> int:
    if not names:
        print("Usage: card_view.py <card_name> [<card_name> ...]", file=sys.stderr)
        return 1

    if cache is None:
        cache = CardCache()
    missing = []
    for name, entry in cache.get_many(names).items():
        if entry is None:
            missing.append(name)
            continue
        card = from_scryfall(entry["scryfall"])
        for warning in card.warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
        print(render(card))

    for name in missing:
        print(f"NOT CACHED: {name}", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
