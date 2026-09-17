import pytest
from lib.card_model import (
    CAST, DISTURB, FLIP, MELD, PREPARED, TRANSFORM, UNKNOWN,
    from_scryfall, mana_value,
)
from lib.scryfall import trim_card

# Fixtures are invented cards that keep the exact JSON shape Scryfall returns for each layout.


def card(scryfall, name):
    # Go through trim_card so tests see exactly what the cache stores
    return from_scryfall(trim_card(scryfall(name)))


# --- Bug #1: root-only fields must survive for every multi-face layout ---

@pytest.mark.parametrize("fixture, cmc, identity", [
    ("transform", 1.0, ("U",)),
    ("transform_battle", 4.0, ("G",)),
    ("modal_dfc", 2.0, ("B", "R")),
    ("modal_dfc_transform", 2.0, ("G", "W")),
    ("adventure", 4.0, ("R",)),
    ("prepare", 2.0, ("B", "W")),
    ("split", 4.0, ("R", "U")),        # combined mana value of both halves
    ("split_room", 8.0, ("B",)),
    ("flip", 1.0, ("W",)),
    ("meld_part", 6.0, ("W",)),
])
def test_cmc_and_color_identity_come_from_card_root(scryfall, fixture, cmc, identity):
    c = card(scryfall, fixture)
    assert c.cmc == cmc
    assert c.color_identity == identity


def test_transform_card_colors_fall_back_to_front_face(scryfall):
    assert card(scryfall, "transform").colors == ("U",)


def test_modal_dfc_faces_keep_their_own_colors(scryfall):
    front, back = card(scryfall, "modal_dfc").faces
    assert front.colors == ("B",)
    assert back.colors == ("B", "R")


def test_every_face_keeps_its_oracle_text(scryfall):
    creature, adventure = card(scryfall, "adventure").faces
    assert "deals 1 damage to each opponent" in creature.oracle_text
    assert "deals 3 damage to target creature" in adventure.oracle_text


def test_back_face_stats_are_kept(scryfall):
    front, back = card(scryfall, "modal_dfc").faces
    assert (front.power, front.toughness) == ("2", "2")
    assert back.loyalty == "4"
    assert card(scryfall, "transform_battle").faces[0].defense == "4"


def test_faces_without_colors_derive_them_from_their_cost(scryfall):
    left, right = card(scryfall, "split").faces
    assert (left.colors, right.colors) == (("R",), ("U",))


# --- How each face is reached ---

@pytest.mark.parametrize("fixture, expected", [
    ("instant", [{CAST}]),
    ("transform", [{CAST}, {TRANSFORM}]),
    ("modal_dfc", [{CAST}, {CAST}]),
    ("modal_dfc_transform", [{CAST}, {CAST, TRANSFORM}]),
    ("transform_disturb", [{CAST}, {TRANSFORM, DISTURB}]),
    ("adventure", [{CAST}, {CAST}]),
    ("prepare", [{CAST}, {PREPARED}]),
    ("split", [{CAST}, {CAST}]),
    ("flip", [{CAST}, {FLIP}]),
    ("meld_part", [{CAST}]),
    ("meld_result", [{MELD}]),
])
def test_face_access_modes(scryfall, fixture, expected):
    assert [set(f.access) for f in card(scryfall, fixture).faces] == expected


def test_prepared_spell_is_not_castable_from_hand(scryfall):
    names = [f.name for f in card(scryfall, "prepare").castable_faces]
    assert names == ["Lantern Scholar"]


def test_modal_dfc_back_face_can_be_cast_or_reached_by_transform(scryfall):
    back = card(scryfall, "modal_dfc_transform").faces[1]
    assert back.is_castable
    assert TRANSFORM in back.access
    assert back.mana_value == 6


def test_unknown_layout_falls_back_to_front_face_and_warns(scryfall):
    raw = trim_card(scryfall("modal_dfc"))
    raw["layout"] = "some_future_layout"
    c = from_scryfall(raw)
    assert [set(f.access) for f in c.faces] == [{CAST}, {UNKNOWN}]
    assert c.cmc == 2.0
    assert any("some_future_layout" in w for w in c.warnings)


def test_known_layouts_do_not_warn(scryfall):
    assert card(scryfall, "prepare").warnings == ()


# --- Single-faced cards ---

def test_single_faced_card(scryfall):
    c = card(scryfall, "instant")
    assert (c.name, c.mana_cost, c.cmc, c.colors) == ("Ember Sting", "{R}", 1.0, ("R",))
    assert c.oracle_text == "Ember Sting deals 2 damage to any target."
    assert c.legalities["modern"] == "legal"


@pytest.mark.parametrize("cost, expected", [
    ("", 0), ("{R}", 1), ("{2}{U}{U}", 4), ("{X}{R}", 1),
    ("{1}{W/B}", 2), ("{2/W}", 2), ("{G/P}", 1), ("{HW}", 0.5), ("{C}", 1),
])
def test_mana_value(cost, expected):
    assert mana_value(cost) == expected
