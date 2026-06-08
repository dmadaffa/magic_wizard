from lib.deck_parser import parse, unique_names


def test_parses_card_quantities():
    deck = parse("4 Cinder Dart\n2 Island")
    assert deck["main"] == [{"qty": 4, "name": "Cinder Dart"}, {"qty": 2, "name": "Island"}]


def test_sideboard_via_comment_marker():
    deck = parse("4 Cinder Dart\n// Sideboard\n2 Gravel Warden")
    assert len(deck["main"]) == 1
    assert deck["side"] == [{"qty": 2, "name": "Gravel Warden"}]


def test_sideboard_via_blank_line():
    deck = parse("4 Cinder Dart\n\n2 Gravel Warden")
    assert deck["side"][0]["name"] == "Gravel Warden"
    assert deck["main"][0]["name"] == "Cinder Dart"


def test_sideboard_via_sb_prefix():
    deck = parse("4 Cinder Dart\nSB: 2 Gravel Warden")
    assert deck["side"][0]["name"] == "Gravel Warden"


def test_comments_not_in_sideboard_are_ignored():
    deck = parse("// Izzet Delver\n4 Cinder Dart")
    assert len(deck["main"]) == 1
    assert deck["side"] == []


def test_accepts_quantity_with_x_suffix():
    deck = parse("4x Cinder Dart")
    assert deck["main"][0] == {"qty": 4, "name": "Cinder Dart"}


def test_empty_input_returns_empty_deck():
    deck = parse("")
    assert deck == {"main": [], "side": []}


def test_unique_names_deduplicates_across_main_and_side():
    text = "4 Cinder Dart\n2 Cinder Dart\n// Sideboard\n2 Cinder Dart"
    names = unique_names(parse(text))
    assert names == ["Cinder Dart"]


def test_unique_names_includes_both_main_and_side():
    text = "4 Cinder Dart\n// Sideboard\n2 Gravel Warden"
    names = unique_names(parse(text))
    assert "Cinder Dart" in names
    assert "Gravel Warden" in names
