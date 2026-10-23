"""Deck statistics: mana curve, color requirements and mana sources.

Functions over Cards with quantities; no I/O. The analysis step reads
the rendered text instead of counting by hand.

Rules:
  - A card is a land when its front face's type line contains "Land". Lands stay
    out of the curve and the average.
  - Every non-land card is counted once, at Scryfall's cmc (front face for
    MDFC/adventure, combined cost for split). X counts as 0. Counts are by copies.
  - Flexibility: a castable face cheaper than the card's cmc, or a castable
    land face (spell // land MDFC).
  - Colors: over the castable faces of non-land cards. A card counts once per
    color for "spells"; "pips" sum every castable face. A hybrid pip counts for
    both colors.
  - Sources: copies of lands plus MDFCs with a castable land face, per color
    they can produce. Nonland producers (rocks, dorks) are listed, not counted.
"""

from dataclasses import dataclass, field

from lib.card_model import COLOR_SYMBOLS as COLORS
from lib.card_model import Card, Face, color_pips

SOURCE_SYMBOLS = (*COLORS, "C")
CURVE_BUCKETS = ("0", "1", "2", "3", "4", "5+")


def _is_land(face: Face) -> bool:
    return "Land" in face.type_line


def _bucket(cmc: float) -> str:
    return "5+" if cmc >= 5 else str(int(cmc))


@dataclass
class DeckStats:
    curve: dict[str, int] = field(default_factory=lambda: dict.fromkeys(CURVE_BUCKETS, 0))
    nonland_count: int = 0
    average_cmc: float = 0.0
    land_count: int = 0
    flexible: list[str] = field(default_factory=list)       # "Card (Face)"
    x_spells: list[str] = field(default_factory=list)
    color_spells: dict[str, int] = field(default_factory=lambda: dict.fromkeys(COLORS, 0))
    color_pips: dict[str, int] = field(default_factory=lambda: dict.fromkeys(COLORS, 0))
    sources: dict[str, int] = field(default_factory=lambda: dict.fromkeys(SOURCE_SYMBOLS, 0))
    nonland_producers: list[str] = field(default_factory=list)


def deck_stats(entries: list[tuple[Card, int]]) -> DeckStats:
    """Stats for (card, copies) pairs, e.g. a deck's main board."""
    stats = DeckStats()
    cmc_total = 0.0
    for card, copies in entries:
        is_land = _is_land(card.faces[0])
        castable_land = not is_land and any(_is_land(f) for f in card.castable_faces)
        if is_land or castable_land:
            for symbol in card.produced_mana:
                if symbol in stats.sources:
                    stats.sources[symbol] += copies
        if is_land:
            stats.land_count += copies
            continue

        stats.nonland_count += copies
        cmc_total += card.cmc * copies
        stats.curve[_bucket(card.cmc)] += copies

        for face in card.castable_faces:
            if _is_land(face) or face.mana_value < card.cmc:
                stats.flexible.append(f"{card.name} ({face.name})")
            if "{X}" in face.mana_cost and card.name not in stats.x_spells:
                stats.x_spells.append(card.name)

        needed = set()
        for face in card.castable_faces:
            for color, count in color_pips(face.mana_cost).items():
                stats.color_pips[color] += count * copies
                if count:
                    needed.add(color)
        for color in needed:
            stats.color_spells[color] += copies

        if card.produced_mana and not castable_land:
            stats.nonland_producers.append(card.name)

    if stats.nonland_count:
        stats.average_cmc = cmc_total / stats.nonland_count
    return stats


def render(stats: DeckStats) -> str:
    """Compact text for the analysis step."""
    def listing(items: list[str]) -> str:
        return "; ".join(items) if items else "none"

    lines = [
        "Curve: " + " ".join(f"{b}={stats.curve[b]}" for b in CURVE_BUCKETS),
        f"Average CMC: {stats.average_cmc:.2f} ({stats.nonland_count} non-land cards)",
        f"Lands: {stats.land_count}",
        "Flexible: " + listing(stats.flexible),
        "X spells: " + listing(stats.x_spells),
        "Colors (spells/pips): "
        + " ".join(f"{c}={stats.color_spells[c]}/{stats.color_pips[c]}" for c in COLORS),
        "Sources: " + " ".join(f"{c}={stats.sources[c]}" for c in SOURCE_SYMBOLS),
        "Nonland mana producers (not counted): " + listing(stats.nonland_producers),
    ]
    return "\n".join(lines)
