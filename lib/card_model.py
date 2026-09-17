"""Interpret stored Scryfall card objects as Cards made of Faces.

The cache stores Scryfall's JSON (trimmed); everything the analysis needs is
derived here, so supporting a new mechanic means editing a table below, not
changing the cache or re-fetching cards.

How a face can be put into play is described by *access modes*:
  - LAYOUT_ACCESS gives the modes implied by the card's layout.
  - KEYWORD_ACCESS adds modes implied by keywords, which matters when a card
    mixes mechanics (e.g. a modal DFC whose front face can also transform into
    its back face).
Only faces with the "cast" mode count as spells you can cast from hand.
"""

import re
from dataclasses import dataclass, field

CAST = "cast"                  # cast from hand for this face's mana cost
TRANSFORM = "transform"        # reached by transforming the other face
FLIP = "flip"                  # Kamigawa flip cards
PREPARED = "prepared"          # copy cast while the creature is prepared
DISTURB = "disturb"            # cast transformed from the graveyard
DAYBOUND = "daybound"          # day/night transform
MORE_THAN_MEETS_THE_EYE = "more_than_meets_the_eye"  # cast transformed
CRAFT = "craft"                # transform via exiling materials
MELD = "meld"                  # a melded permanent, never cast
UNKNOWN = "unknown"            # layout we have no rule for yet

# Access modes per face index, keyed by Scryfall `layout`.
LAYOUT_ACCESS: dict[str, tuple[frozenset[str], ...]] = {
    "normal":          (frozenset({CAST}),),
    "leveler":         (frozenset({CAST}),),
    "class":           (frozenset({CAST}),),
    "case":            (frozenset({CAST}),),
    "saga":            (frozenset({CAST}),),
    "mutate":          (frozenset({CAST}),),
    "prototype":       (frozenset({CAST}),),
    "meld":            (frozenset({CAST}),),
    "host":            (frozenset({CAST}),),
    "augment":         (frozenset({CAST}),),
    "transform":       (frozenset({CAST}), frozenset({TRANSFORM})),
    "modal_dfc":       (frozenset({CAST}), frozenset({CAST})),
    "adventure":       (frozenset({CAST}), frozenset({CAST})),
    "split":           (frozenset({CAST}), frozenset({CAST})),
    "flip":            (frozenset({CAST}), frozenset({FLIP})),
    "prepare":         (frozenset({CAST}), frozenset({PREPARED})),
    "reversible_card": (frozenset({CAST}), frozenset({CAST})),
}
# Faces beyond what a rule lists, or cards with an unknown layout.
_FALLBACK_ACCESS = (frozenset({CAST}),)
_EXTRA_FACE_ACCESS = frozenset({UNKNOWN})

# Keyword -> (face index gaining the mode, mode).
KEYWORD_ACCESS: dict[str, tuple[int, str]] = {
    "Transform": (1, TRANSFORM),
    "Disturb": (1, DISTURB),
    "Daybound": (1, DAYBOUND),
    "More Than Meets the Eye": (1, MORE_THAN_MEETS_THE_EYE),
    "Craft": (1, CRAFT),
}

_SYMBOL_RE = re.compile(r"\{([^}]+)\}")
_COLOR_SYMBOLS = ("W", "U", "B", "R", "G")


def mana_value(mana_cost: str) -> float:
    """Mana value of a printed cost, e.g. '{2}{W/U}{R/P}' -> 4."""
    total = 0.0
    for symbol in _SYMBOL_RE.findall(mana_cost or ""):
        if symbol.isdigit():
            total += int(symbol)
        elif symbol in ("X", "Y", "Z"):
            continue
        elif symbol.startswith("H"):  # half mana, e.g. {HW}
            total += 0.5
        elif "/" in symbol:
            first = symbol.split("/")[0]
            total += int(first) if first.isdigit() else 1  # {2/W} counts 2
        else:
            total += 1
    return total


def _colors_in_cost(mana_cost: str) -> tuple[str, ...]:
    found = {c for s in _SYMBOL_RE.findall(mana_cost or "") for c in _COLOR_SYMBOLS if c in s.split("/")}
    return tuple(c for c in _COLOR_SYMBOLS if c in found)


@dataclass(frozen=True)
class Face:
    name: str
    mana_cost: str
    type_line: str
    oracle_text: str
    colors: tuple[str, ...]
    access: frozenset[str]
    power: str = ""
    toughness: str = ""
    loyalty: str = ""
    defense: str = ""

    @property
    def mana_value(self) -> float:
        return mana_value(self.mana_cost)

    @property
    def is_castable(self) -> bool:
        return CAST in self.access


@dataclass(frozen=True)
class Card:
    name: str
    layout: str
    cmc: float
    mana_cost: str
    type_line: str
    colors: tuple[str, ...]
    color_identity: tuple[str, ...]
    keywords: tuple[str, ...]
    legalities: dict[str, str]
    faces: tuple[Face, ...]
    warnings: tuple[str, ...] = field(default=())

    @property
    def castable_faces(self) -> tuple[Face, ...]:
        return tuple(f for f in self.faces if f.is_castable)

    @property
    def oracle_text(self) -> str:
        return "\n//\n".join(f.oracle_text for f in self.faces)


def _face_access(layout: str, keywords: tuple[str, ...], face_count: int, raw: dict) -> list[set[str]]:
    rule = LAYOUT_ACCESS.get(layout, _FALLBACK_ACCESS)
    access = [set(rule[i]) if i < len(rule) else set(_EXTRA_FACE_ACCESS) for i in range(face_count)]
    for keyword in keywords:
        if keyword in KEYWORD_ACCESS:
            index, mode = KEYWORD_ACCESS[keyword]
            if index < face_count:
                access[index].add(mode)
    if layout == "meld" and any(
        p.get("component") == "meld_result" and p.get("name") == raw.get("name")
        for p in raw.get("all_parts", [])
    ):
        access[0] = {MELD}
    return access


def from_scryfall(raw: dict) -> Card:
    """Build a Card from a (trimmed) Scryfall card object."""
    layout = raw.get("layout", "normal")
    keywords = tuple(raw.get("keywords", []))
    raw_faces = raw.get("card_faces") or [raw]
    root_colors = tuple(raw.get("colors", ()))

    warnings = []
    if layout not in LAYOUT_ACCESS:
        warnings.append(f"{raw.get('name')}: unknown layout {layout!r}, treating only the first face as castable")

    access = _face_access(layout, keywords, len(raw_faces), raw)
    faces = []
    for raw_face, modes in zip(raw_faces, access):
        cost = raw_face.get("mana_cost", "")
        if "colors" in raw_face:
            colors = tuple(raw_face["colors"])
        else:
            colors = _colors_in_cost(cost) or root_colors
        faces.append(Face(
            name=raw_face.get("name", ""),
            mana_cost=cost,
            type_line=raw_face.get("type_line", ""),
            oracle_text=raw_face.get("oracle_text", ""),
            colors=colors,
            access=frozenset(modes),
            power=raw_face.get("power") or "",
            toughness=raw_face.get("toughness") or "",
            loyalty=raw_face.get("loyalty") or "",
            defense=raw_face.get("defense") or "",
        ))
    front = faces[0]

    if "cmc" in raw:
        cmc = float(raw["cmc"])
    elif "cmc" in raw_faces[0]:
        cmc = float(raw_faces[0]["cmc"])
    else:
        cmc = front.mana_value

    if "color_identity" in raw:
        identity = tuple(raw["color_identity"])
    else:
        seen = {c for f in faces for c in f.colors}
        identity = tuple(c for c in _COLOR_SYMBOLS if c in seen)

    return Card(
        name=raw.get("name", ""),
        layout=layout,
        cmc=cmc,
        mana_cost=raw.get("mana_cost", front.mana_cost),
        type_line=raw.get("type_line", front.type_line),
        colors=root_colors if "colors" in raw else front.colors,
        color_identity=identity,
        keywords=keywords,
        legalities=dict(raw.get("legalities", {})),
        faces=tuple(faces),
        warnings=tuple(warnings),
    )
